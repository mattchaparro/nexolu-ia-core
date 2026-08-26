"""Trazabilidad y reintento manual de invocaciones de herramientas fallidas.

Protegido con `require_platform_access`, igual que `/v1/admin/apps` -- ninguna
app integradora conoce esta key. El reintento relee la `AppRegistration`
vigente (respeta una rotacion de key posterior al fallo original) y vuelve a
llamar a `AppToolClient.invoke()` con los mismos `arguments` y el
`TenantContext` que se guardo en el momento del fallo. No muta el log
original: escribe uno nuevo, igual que Payment Core deja rastro de cada
intento de entrega de webhook en vez de sobreescribir el anterior.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import require_platform_access
from nexolu_ia_core.core.auth.repository import AppRegistrationRepository
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.schemas import TenantContext, ToolInvocationLogOut
from nexolu_ia_core.core.tools.dispatch_client import AppToolClient, ToolDispatchError

router = APIRouter(
    prefix="/v1/admin/tool-logs",
    tags=["admin"],
    dependencies=[Depends(require_platform_access)],
)


@router.get("", response_model=list[ToolInvocationLogOut])
async def list_tool_logs(
    app_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[ToolInvocationLogOut]:
    logs = await ConversationRepository(session).list_tool_logs(
        app_id=app_id, status=status_filter, limit=limit, offset=offset
    )
    return [ToolInvocationLogOut.model_validate(log, from_attributes=True) for log in logs]


@router.post("/{log_id}/retry", response_model=ToolInvocationLogOut)
async def retry_tool_log(log_id: int, session: AsyncSession = Depends(get_session)) -> ToolInvocationLogOut:
    repo = ConversationRepository(session)
    log = await repo.get_tool_log(log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro no encontrado.")
    if log.status == "ok":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este registro ya fue exitoso.")
    if not log.context:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este registro no tiene contexto guardado (es anterior a esta funcionalidad) "
                "y no se puede reintentar automaticamente."
            ),
        )

    registration = await AppRegistrationRepository(session).get_by_app_id(log.app_id)
    if registration is None or not registration.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"App '{log.app_id}' no existe o esta inactiva."
        )

    app = AppIdentity(
        app_id=registration.app_id,
        api_key=registration.api_key,
        base_url=registration.base_url,
        name=registration.name or registration.app_id,
    )
    context = TenantContext(**log.context)
    client = AppToolClient(app)

    try:
        data = await client.invoke(log.tool_name, log.arguments, context)
    except ToolDispatchError as exc:
        new_log = await repo.log_tool_invocation(
            conversation_id=log.conversation_id,
            app_id=log.app_id,
            business_id=log.business_id,
            tool_name=log.tool_name,
            arguments=log.arguments,
            status="error",
            result_summary=str(exc)[:500],
            context=log.context,
        )
    else:
        new_log = await repo.log_tool_invocation(
            conversation_id=log.conversation_id,
            app_id=log.app_id,
            business_id=log.business_id,
            tool_name=log.tool_name,
            arguments=log.arguments,
            status="ok",
            result_summary=json.dumps(data, ensure_ascii=False)[:500],
            context=log.context,
        )

    await session.commit()
    return ToolInvocationLogOut.model_validate(new_log, from_attributes=True)
