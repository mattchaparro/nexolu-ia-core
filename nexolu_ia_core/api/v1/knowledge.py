"""Las preguntas frecuentes de cada negocio, administradas por su app.

La app (spa, POS...) es quien sabe quién puede editar: este endpoint
confía en ella porque la llamada viene firmada con SU llave, y acota todo
a su `app_id` y al `business_id` que manda. Un negocio del spa nunca ve ni
toca el conocimiento de otro, ni el de otra app.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import get_current_app
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.entities import KnowledgeEntry
from nexolu_ia_core.core.rag.knowledge import KnowledgeRepository

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class KnowledgeIn(BaseModel):
    business_id: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=2, max_length=160)
    answer: str = Field(min_length=2, max_length=4000)
    is_active: bool = True


class KnowledgePatch(BaseModel):
    business_id: str = Field(min_length=1, max_length=64)
    topic: str | None = Field(default=None, min_length=2, max_length=160)
    answer: str | None = Field(default=None, min_length=2, max_length=4000)
    is_active: bool | None = None


class KnowledgeOut(BaseModel):
    id: str
    topic: str
    answer: str
    is_active: bool
    updated_at: datetime

    @classmethod
    def of(cls, entry: KnowledgeEntry) -> KnowledgeOut:
        return cls(
            id=entry.id,
            topic=entry.topic,
            answer=entry.answer,
            is_active=entry.is_active,
            updated_at=entry.updated_at,
        )


@router.get("")
async def list_knowledge(
    business_id: str = Query(min_length=1, max_length=64),
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeOut]:
    entries = await KnowledgeRepository(session).list(app.app_id, business_id)
    return [KnowledgeOut.of(e) for e in entries]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    payload: KnowledgeIn,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeOut:
    entry = await KnowledgeRepository(session).create(
        app_id=app.app_id,
        business_id=payload.business_id,
        topic=payload.topic.strip(),
        answer=payload.answer.strip(),
        is_active=payload.is_active,
    )
    await session.commit()
    return KnowledgeOut.of(entry)


@router.patch("/{entry_id}")
async def update_knowledge(
    entry_id: str,
    payload: KnowledgePatch,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeOut:
    repo = KnowledgeRepository(session)
    entry = await repo.get(entry_id, app.app_id, payload.business_id)

    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe esa entrada.")

    if payload.topic is not None:
        entry.topic = payload.topic.strip()
    if payload.answer is not None:
        entry.answer = payload.answer.strip()
    if payload.is_active is not None:
        entry.is_active = payload.is_active
    entry.updated_at = datetime.utcnow()

    await session.commit()
    return KnowledgeOut.of(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    entry_id: str,
    business_id: str = Query(min_length=1, max_length=64),
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = KnowledgeRepository(session)
    entry = await repo.get(entry_id, app.app_id, business_id)

    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe esa entrada.")

    await repo.delete(entry)
    await session.commit()
