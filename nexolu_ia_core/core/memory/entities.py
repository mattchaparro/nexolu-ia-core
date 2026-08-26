"""Modelos de persistencia del Core.

Deliberadamente NO hay tabla de negocio aca (sin `productos`, sin `ventas`):
eso vive en MySQL, del lado de cada aplicacion. Lo que el Core persiste es
memoria conversacional, auditoria de que herramientas se ejecutaron, uso/costo
agregado y borradores de escritura pendientes de confirmar -- el estado que
le pertenece al motor de IA, no al negocio.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexolu_ia_core.core.memory.db import Base
from nexolu_ia_core.core.security.api_keys import generate_api_key, hash_api_key
from nexolu_ia_core.core.security.crypto import EncryptedString


def _uuid() -> str:
    return uuid.uuid4().hex


class AppRegistration(Base):
    """Aplicacion cliente autorizada a consumir el Core (POS, Spa,
    EasyTickets...). Unica fuente de verdad de identidad de apps -- ver
    `core/auth/apps.py` y `core/auth/repository.py`.

    `api_key` se guarda cifrada (no en texto plano) porque el Core la
    reenvia tal cual como `Authorization: Bearer` cuando llama de vuelta al
    backend de la app para ejecutar herramientas (ver
    `core/tools/dispatch_client.py`); `api_key_hash` es lo que se usa para
    autenticar la llamada ENTRANTE, en tiempo constante, sin tener que
    descifrar nada en el camino caliente (ver `core/auth/apps.py`). Mismo
    patron que `Integration` en nexolu-payments-core.
    """

    __tablename__ = "app_registrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    app_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    api_key: Mapped[str] = mapped_column(EncryptedString(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    base_url: Mapped[str] = mapped_column(String(512))
    site_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    site_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # provider/model/provider_api_key son opcionales: una app que no los
    # declara usa el default global (DEFAULT_PROVIDER/DEFAULT_MODEL y la API
    # key global de ese proveedor). Declararlos permite que, por ejemplo, el
    # POS use un modelo barato con su propio workspace de OpenRouter y el
    # Spa use uno mas potente con el suyo. Ver ModelRouter.resolve().
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_api_key: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    # Configuracion de ruteo avanzado de OpenRouter (order, allow_fallbacks,
    # data_collection...), inyectada tal cual en el campo `provider` del
    # payload de chat/completions. Ver providers/openrouter.py.
    provider_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __init__(self, **kwargs):
        api_key = kwargs.pop("api_key", None) or generate_api_key()
        self.api_key = api_key
        self.api_key_hash = hash_api_key(api_key)
        super().__init__(**kwargs)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_tenant", "app_id", "business_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    app_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), default="")
    created_by_channel: Mapped[str] = mapped_column(String(32), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list[Message]] = relationship(back_populates="conversation", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation", "conversation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    app_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32), default="web")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Texto NUESTRO de contingencia (p.ej. "respuesta_vacia"), no un error del
    # modelo. Marca los turnos que no deben reenviarse como historial de
    # ejemplo: reenviarlos le enseña al modelo a imitar la contingencia. Ver
    # la misma trampa documentada en AiChatService::turnosDesdeMensajes (POS).
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ToolInvocationLog(Base):
    """Auditoria completa de cada llamada a herramienta: que se pidio, que
    respondio la aplicacion, y si fallo. Separada de `Message` (que es lo que
    ve el modelo) porque esto es para observabilidad/soporte, y puede crecer
    o cambiar de forma sin afectar el historial de chat."""

    __tablename__ = "tool_invocation_logs"
    __table_args__ = (Index("ix_tool_logs_tenant", "app_id", "business_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    app_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))  # "ok" | "error"
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UsageDaily(Base):
    """Consumo agregado por app+tenant+dia. El Core siempre registra esto,
    sin importar el plan comercial: la logica de cuotas/facturacion es de
    cada producto (ver Contexto en el plan), pero los datos crudos de
    consumo tienen que existir en un solo lugar para que cualquiera pueda
    facturar sobre ellos."""

    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("app_id", "business_id", "date", name="uq_usage_daily_tenant_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(64))
    date: Mapped[date_type] = mapped_column(Date)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)


class Draft(Base):
    """Borrador de una herramienta de escritura, pendiente de confirmacion
    humana. Ver `core/tools/base.py::WriteTool`."""

    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_tenant", "app_id", "business_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    app_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    draft_type: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|confirmed|discarded|expired
    payload: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
