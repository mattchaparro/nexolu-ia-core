"""Confirmacion humana de una herramienta de escritura.

Este es el unico camino por el que un `WriteTool` llega a ejecutarse de
verdad: el modelo nunca llama directo al despacho de la app para una
escritura, solo crea el borrador (ver `ChatOrchestrator._execute_tool`).
Confirmar es lo que dispara la llamada real via `AppToolClient`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.apps.registry import get_app_bundle
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import get_current_app
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.schemas import TenantContext
from nexolu_ia_core.core.tools.dispatch_client import AppToolClient, ToolDispatchError
from nexolu_ia_core.core.tools.exceptions import ToolInputException, ToolNotAllowedException
from nexolu_ia_core.core.tools.guard import ToolGuard
from nexolu_ia_core.core.tools.remote_catalog import get_remote_tool_catalog

router = APIRouter(prefix="/v1/drafts", tags=["drafts"])


class DraftActionIn(BaseModel):
    context: TenantContext
    # Valores editados en la tarjeta de confirmacion. Si no vienen, se usa el
    # payload original que genero la herramienta.
    values: dict[str, Any] | None = None


async def _load_pending_draft(draft_id: str, app: AppIdentity, context: TenantContext, session: AsyncSession):
    repo = ConversationRepository(session)
    draft = await repo.get_draft(draft_id, app.app_id, context.business_id)

    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrador no encontrado.")

    if draft.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El borrador ya esta en estado '{draft.status}'.",
        )

    return draft, repo


@router.post("/{draft_id}/confirm")
async def confirm_draft(
    draft_id: str,
    payload: DraftActionIn,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> dict:
    context = payload.context.resolved(app.app_id)
    draft, _repo = await _load_pending_draft(draft_id, app, context, session)

    bundle = get_app_bundle(app.app_id)
    await get_remote_tool_catalog().sync(bundle.tools, app)

    try:
        tool = bundle.tools.resolve_for(context, draft.tool_name)
    except ToolNotAllowedException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    raw_values = payload.values if payload.values is not None else draft.payload

    try:
        arguments = ToolGuard().sanitize(tool, context, raw_values)
    except ToolInputException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    client = AppToolClient(app)
    try:
        data = await client.invoke(tool.name, arguments, context)
    except ToolDispatchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    draft.status = "confirmed"
    await session.commit()

    return {"status": "confirmed", "data": data}


@router.post("/{draft_id}/discard")
async def discard_draft(
    draft_id: str,
    payload: DraftActionIn,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> dict:
    draft, _repo = await _load_pending_draft(draft_id, app, payload.context.resolved(app.app_id), session)

    draft.status = "discarded"
    await session.commit()

    return {"status": "discarded"}
