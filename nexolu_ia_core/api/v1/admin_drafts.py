"""Auditoria administrativa de borradores (drafts) de todas las apps/tenants.

Protegido con `require_platform_access`, igual que `/v1/admin/apps`. `purge` es
un discard forzado: a diferencia de `POST /v1/drafts/{id}/discard` (que exige
la api key de la propia app y solo alcanza a su propio tenant), este endpoint
no esta acotado a una app/tenant -- pensado para soporte/incidentes, no para
el flujo normal de confirmacion humana.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.dependencies import require_platform_access
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.schemas import DraftAdminOut

router = APIRouter(
    prefix="/v1/admin/drafts",
    tags=["admin"],
    dependencies=[Depends(require_platform_access)],
)


@router.get("", response_model=list[DraftAdminOut])
async def list_drafts(
    app_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[DraftAdminOut]:
    drafts = await ConversationRepository(session).list_drafts(
        app_id=app_id, status=status_filter, limit=limit, offset=offset
    )
    return [DraftAdminOut.model_validate(draft, from_attributes=True) for draft in drafts]


@router.post("/{draft_id}/purge", response_model=DraftAdminOut)
async def purge_draft(draft_id: str, session: AsyncSession = Depends(get_session)) -> DraftAdminOut:
    repo = ConversationRepository(session)
    draft = await repo.get_draft_by_id(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrador no encontrado.")
    if draft.status in ("confirmed", "discarded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"El borrador ya esta en estado '{draft.status}'."
        )

    draft.status = "discarded"
    await session.commit()
    return DraftAdminOut.model_validate(draft, from_attributes=True)
