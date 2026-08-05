"""Acceso a datos del Core (conversaciones, mensajes, borradores, uso).

Una sola clase con toda la persistencia del orquestador: no hay necesidad de
repositorios separados todavia, y una clase por tabla hoy solo agregaria
indireccion sin compradores (YAGNI). Si el Core crece a necesitar
transacciones mas finas por entidad, se separa entonces.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.memory.entities import (
    Conversation,
    Draft,
    Message,
    ToolInvocationLog,
    UsageDaily,
)
from nexolu_ia_core.core.schemas import TenantContext


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        *,
        app_id: str,
        context: TenantContext,
        agent: str,
        conversation_id: str | None,
        first_text: str,
    ) -> Conversation:
        if conversation_id is not None:
            # Filtro explicito por app + business + user: aunque el id venga
            # del request, nadie puede abrir la conversacion de otro tenant.
            stmt = select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.app_id == app_id,
                Conversation.business_id == context.business_id,
                Conversation.user_id == context.user_id,
            )
            existing = (await self._session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return existing

        conversation = Conversation(
            app_id=app_id,
            business_id=context.business_id,
            user_id=context.user_id,
            agent=agent,
            title=first_text[:60],
            created_by_channel=context.channel,
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def touch(self, conversation: Conversation) -> None:
        conversation.last_message_at = datetime.utcnow()
        await self._session.flush()

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(reversed(rows))

    async def add_message(self, **fields) -> Message:
        message = Message(**fields)
        self._session.add(message)
        await self._session.flush()
        return message

    async def create_draft(self, **fields) -> Draft:
        draft = Draft(**fields)
        self._session.add(draft)
        await self._session.flush()
        return draft

    async def get_draft(self, draft_id: str, app_id: str, business_id: str) -> Draft | None:
        stmt = select(Draft).where(
            Draft.id == draft_id, Draft.app_id == app_id, Draft.business_id == business_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def log_tool_invocation(self, **fields) -> ToolInvocationLog:
        log = ToolInvocationLog(**fields)
        self._session.add(log)
        await self._session.flush()
        return log

    async def record_usage(
        self, *, app_id: str, business_id: str, input_tokens: int, output_tokens: int, cost_micros: int
    ) -> None:
        today = date.today()
        stmt = select(UsageDaily).where(
            UsageDaily.app_id == app_id, UsageDaily.business_id == business_id, UsageDaily.date == today
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()

        if row is None:
            # Los defaults del modelo solo se aplican al insertar en la BD, no
            # al construir el objeto en Python: sin estos valores explicitos,
            # sumar `+= 1` mas abajo falla con None antes del primer flush.
            row = UsageDaily(
                app_id=app_id,
                business_id=business_id,
                date=today,
                message_count=0,
                input_tokens=0,
                output_tokens=0,
                cost_micros=0,
            )
            self._session.add(row)

        row.message_count += 1
        row.input_tokens += input_tokens
        row.output_tokens += output_tokens
        row.cost_micros += cost_micros
        await self._session.flush()

    async def usage_today(self, app_id: str, business_id: str) -> UsageDaily | None:
        stmt = select(UsageDaily).where(
            UsageDaily.app_id == app_id,
            UsageDaily.business_id == business_id,
            UsageDaily.date == date.today(),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def expire_stale_drafts(self, older_than: timedelta = timedelta(hours=24)) -> None:
        """Housekeeping simple; no se llama automaticamente todavia -- queda
        disponible para un job periodico cuando exista un scheduler en el
        servicio."""
        cutoff = datetime.utcnow() - older_than
        stmt = select(Draft).where(Draft.status == "pending", Draft.created_at < cutoff)
        for draft in (await self._session.execute(stmt)).scalars():
            draft.status = "expired"
        await self._session.flush()
