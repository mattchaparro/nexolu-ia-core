"""Endpoint principal: un mensaje entra, el orquestador decide todo lo demas.

Que aplicacion esta llamando sale de la API key (`get_current_app`), nunca
del body: asi ninguna aplicacion puede hacerse pasar por otra ni leer las
herramientas de un producto que no es el suyo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.apps.registry import get_app_bundle
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import get_current_app
from nexolu_ia_core.core.chat.orchestrator import ChatOrchestrator
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.models.router import ModelRouter
from nexolu_ia_core.core.schemas import ChatMessageIn, ChatMessageOut
from nexolu_ia_core.core.tools.remote_catalog import get_remote_tool_catalog
from nexolu_ia_core.providers.registry import get_provider_registry

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatMessageOut)
async def send_chat_message(
    payload: ChatMessageIn,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> ChatMessageOut:
    try:
        bundle = get_app_bundle(app.app_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await get_remote_tool_catalog().sync(bundle.tools, app)

    try:
        agent = bundle.agents.get(payload.agent)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    orchestrator = ChatOrchestrator(
        repository=ConversationRepository(session),
        provider_registry=get_provider_registry(),
        model_router=ModelRouter(),
    )

    try:
        result = await orchestrator.send_message(
            app_identity=app,
            app_display_name=bundle.display_name,
            tool_registry=bundle.tools,
            agent=agent,
            context=payload.context,
            message=payload.message,
            conversation_id=payload.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await session.commit()
    return result
