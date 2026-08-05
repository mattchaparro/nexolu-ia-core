from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import get_current_app
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.entities import Conversation, Message

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    business_id: str = Query(...),
    user_id: str = Query(...),
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.app_id == app.app_id,
        Conversation.business_id == business_id,
        Conversation.user_id == user_id,
    )
    conversation = (await session.execute(stmt)).scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversacion no encontrada.")

    messages_stmt = (
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )
    messages = (await session.execute(messages_stmt)).scalars().all()

    return {
        "id": conversation.id,
        "agent": conversation.agent,
        "created_by_channel": conversation.created_by_channel,
        "last_message_at": conversation.last_message_at,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "created_at": m.created_at,
            }
            for m in messages
            if m.error is None
        ],
    }
