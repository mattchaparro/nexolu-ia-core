"""DTOs neutrales del Core.

Estos tipos son el "idioma comun" entre el orquestador de chat, los
proveedores de IA y las aplicaciones cliente. Ninguno de ellos conoce nada
especifico de un producto: un `ChatTurn` es el mismo objeto sin importar si
la conversacion nacio en el POS, el Spa o EasyTickets.

Equivalen a `app/Services/Ai/Dto/*.php` en el POS actual.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """Una invocacion de herramienta que el modelo pidio."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Lo que se le describe al modelo sobre una herramienta disponible."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    """Un turno de la conversacion, en formato neutral (no el de ningun proveedor)."""

    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None

    @classmethod
    def user(cls, content: str) -> ChatTurn:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str | None, tool_calls: list[ToolCall] | None = None) -> ChatTurn:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, tool_call_id: str, tool_name: str, content: str) -> ChatTurn:
        return cls(role=Role.TOOL, tool_call_id=tool_call_id, tool_name=tool_name, content=content)


class ChatRequest(BaseModel):
    """Lo que el orquestador le manda a un `ChatProvider`."""

    system: str
    messages: list[ChatTurn]
    tools: list[ToolDefinition] = Field(default_factory=list)
    max_tokens: int = 1500
    reasoning: bool = False


class ChatResult(BaseModel):
    """Lo que un `ChatProvider` devuelve, ya normalizado."""

    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str | None = None
    cached_tokens: int = 0
    # Costo real en micro-dolares (1_000_000 = US$1) si el proveedor lo reporta.
    # None (no cero) cuando el proveedor no informa costo: distinguir "no se
    # sabe" de "cero" evita que un proveedor mudo se sume como gratis.
    cost_micros: int | None = None

    def wants_tools(self) -> bool:
        return len(self.tool_calls) > 0

    def cache_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return self.cached_tokens / self.input_tokens


class ChatStreamEvent(BaseModel):
    """Un fragmento de `ChatProvider.chat_stream()`.

    `delta` llega repetidas veces conforme el proveedor manda texto; el
    ultimo evento trae `done=True` y `result` con el `ChatResult` completo
    (tool_calls acumuladas, usage, costo) -- equivalente a lo que `chat()`
    devuelve de una sola vez.
    """

    delta: str | None = None
    done: bool = False
    result: ChatResult | None = None


class TenantContext(BaseModel):
    """Lo que la aplicacion llamante afirma sobre quien esta hablando.

    El Core no tiene sesion de usuario ni tabla de permisos propia: confia en
    que la app (Laravel) ya resolvio esto contra su propia base de datos, tal
    como hoy hace `AiToolContext`/`ToolRegistry::availableFor` dentro del POS.
    La app firma la llamada completa con su API key (ver core/auth), asi que
    esta aserción viaja autenticada por app, no por el usuario final.
    """

    # Clave de particion OPACA (conversaciones, drafts, uso/costo) - el Core
    # nunca la valida contra nada propio, no tiene que significar "negocio"
    # literal (mismo patron que nexolu-comms-api). Una app sin concepto de
    # tenant (un solo cliente, sin sub-negocios) puede omitirla: cada
    # endpoint la resuelve a su propio app_id via `resolved()` antes de usarla.
    business_id: str | None = None
    user_id: str
    is_admin: bool = False
    permissions: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    channel: str = "web"
    timezone: str = "America/Bogota"
    locale: str = "es"

    def resolved(self, app_id: str) -> TenantContext:
        """Copia con business_id resuelto: si la app no mando uno, cae al
        propio app_id - asi toda su actividad queda bajo una sola particion
        en vez de fallar por falta de un dato que no le aplica."""
        return self if self.business_id else self.model_copy(update={"business_id": app_id})


class ChatMessageIn(BaseModel):
    """Payload de entrada de POST /v1/chat."""

    conversation_id: str | None = None
    agent: str
    message: str
    context: TenantContext


class DraftOut(BaseModel):
    id: str
    tool_type: str
    status: str
    summary: str
    fields: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)


class ChatMessageOut(BaseModel):
    """Respuesta de POST /v1/chat."""

    conversation_id: str
    text: str
    tools_used: list[str] = Field(default_factory=list)
    drafts: list[DraftOut] = Field(default_factory=list)


class ChatStreamChunk(BaseModel):
    """Un evento de POST /v1/chat/stream, serializado como `data: <json>` de
    SSE. `delta` llega repetidas veces con fragmentos de texto; el ultimo
    evento trae `done=True` con el resto de metadata (equivalente a
    `ChatMessageOut`, pero `text` ahi es el texto COMPLETO acumulado, util
    para un cliente que se conecto tarde o quiere el valor final de una)."""

    delta: str | None = None
    done: bool = False
    conversation_id: str | None = None
    text: str | None = None
    tools_used: list[str] = Field(default_factory=list)
    drafts: list[DraftOut] = Field(default_factory=list)


class CompletionIn(BaseModel):
    """Payload de entrada de POST /v1/completions.

    A diferencia de /v1/chat, no hay conversacion ni herramientas: la app
    llamante ya calculo sus propios numeros (ver AiInsightDefinition en el
    POS) y solo necesita que el modelo los redacte en un system+user prompt
    de una sola pasada, sin historial que persistir.
    """

    system: str
    user: str
    context: TenantContext
    max_tokens: int = 400


class CompletionOut(BaseModel):
    """Respuesta de POST /v1/completions."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_micros: int | None = None


class AppRegistrationIn(BaseModel):
    """Payload de POST /v1/admin/apps."""

    app_id: str
    name: str = ""
    base_url: str
    site_url: str | None = None
    site_name: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_api_key: str | None = None
    provider_preferences: dict[str, Any] = Field(default_factory=dict)


class AppRegistrationPatch(BaseModel):
    """Payload de PATCH /v1/admin/apps/{id}. Todo opcional: solo se
    actualiza lo que venga distinto de None."""

    name: str | None = None
    base_url: str | None = None
    site_url: str | None = None
    site_name: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_api_key: str | None = None
    provider_preferences: dict[str, Any] | None = None
    is_active: bool | None = None


class AppRegistrationOut(BaseModel):
    """Una app tal como la ve el admin -- la key SIEMPRE enmascarada, nunca
    se vuelve a mostrar en claro despues de crearla/regenerarla."""

    id: str
    app_id: str
    name: str
    api_key_masked: str
    is_active: bool
    base_url: str
    site_url: str | None = None
    site_name: str | None = None
    provider: str | None = None
    model: str | None = None
    has_provider_api_key: bool = False
    provider_preferences: dict[str, Any] = Field(default_factory=dict)


class AppRegistrationCreatedOut(AppRegistrationOut):
    """Solo la respuesta de creacion/regeneracion trae la key en claro."""

    api_key: str
