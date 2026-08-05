"""Pruebas del loop historial -> herramientas -> respuesta.

Usa un `ScriptedProvider` (doble de prueba, no vive en el paquete) que
devuelve una secuencia fija de `ChatResult`, para poder afirmar exactamente
que hizo el orquestador en cada iteracion sin depender de un proveedor real.
"""
from __future__ import annotations

import pytest

from nexolu_ia_core.apps.pos.agents import build_agent_registry
from nexolu_ia_core.apps.pos.tools import build_tool_registry
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.chat.orchestrator import ChatOrchestrator
from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.models.router import ModelRouter
from nexolu_ia_core.core.schemas import ChatRequest, ChatResult, TenantContext, ToolCall
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.registry import ProviderRegistry

APP = AppIdentity(app_id="pos", api_key="dev-pos-key", base_url="http://pos.test", name="Nexolu POS")
ADMIN_CONTEXT = TenantContext(business_id="b1", user_id="u1", is_admin=True)


class ScriptedProvider(ChatProvider):
    """Devuelve una respuesta distinta cada vez que se le llama, en orden."""

    def __init__(self, responses: list[ChatResult]) -> None:
        self._responses = list(responses)
        self.calls: list[ChatRequest] = []

    def name(self) -> str:
        return "scripted"

    def model(self) -> str:
        return "scripted-model"

    async def chat(self, request: ChatRequest) -> ChatResult:
        self.calls.append(request)
        return self._responses.pop(0)


class FixedProviderRegistry(ProviderRegistry):
    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    def resolve(self, name: str, model_override: str | None = None) -> ChatProvider:
        return self._provider


@pytest.fixture
async def session():
    await init_models()
    async with get_sessionmaker()() as s:
        yield s
    await get_engine().dispose()


async def test_read_tool_round_trip(session, httpx_mock):
    httpx_mock.add_response(
        url="http://pos.test/api/ai/tools/invoke",
        json={"data": {"abierta": True, "saldo": 150000}},
    )

    provider = ScriptedProvider(
        [
            ChatResult(
                text=None,
                tool_calls=[ToolCall(id="call_1", name="estado_caja", arguments={})],
                input_tokens=50,
                output_tokens=10,
                model="scripted-model",
            ),
            ChatResult(text="La caja esta abierta con $150.000.", input_tokens=60, output_tokens=15, model="scripted-model"),
        ]
    )

    orchestrator = ChatOrchestrator(
        repository=ConversationRepository(session),
        provider_registry=FixedProviderRegistry(provider),
        model_router=ModelRouter(),
    )

    result = await orchestrator.send_message(
        app_identity=APP,
        app_display_name="Nexolu POS",
        tool_registry=build_tool_registry(),
        agent=build_agent_registry().get("cajero"),
        context=ADMIN_CONTEXT,
        message="Como esta la caja?",
        conversation_id=None,
    )

    assert result.tools_used == ["estado_caja"]
    assert "150.000" in result.text
    assert result.drafts == []

    dispatched = httpx_mock.get_requests()[0]
    assert dispatched.headers["Authorization"] == "Bearer dev-pos-key"

    repo = ConversationRepository(session)
    usage = await repo.usage_today("pos", "b1")
    assert usage.message_count == 1
    assert usage.input_tokens == 110
    assert usage.output_tokens == 25


async def test_write_tool_creates_draft_without_calling_app(session, httpx_mock):
    provider = ScriptedProvider(
        [
            ChatResult(
                text=None,
                tool_calls=[
                    ToolCall(id="call_1", name="crear_gasto", arguments={"concepto": "Papeleria", "monto": 25000})
                ],
                model="scripted-model",
            ),
            ChatResult(text="Listo, revisa el borrador y confirma.", model="scripted-model"),
        ]
    )

    orchestrator = ChatOrchestrator(
        repository=ConversationRepository(session),
        provider_registry=FixedProviderRegistry(provider),
        model_router=ModelRouter(),
    )

    result = await orchestrator.send_message(
        app_identity=APP,
        app_display_name="Nexolu POS",
        tool_registry=build_tool_registry(),
        agent=build_agent_registry().get("cajero"),
        context=ADMIN_CONTEXT,
        message="Registra un gasto de papeleria por 25000",
        conversation_id=None,
    )

    assert result.tools_used == ["crear_gasto"]
    assert len(result.drafts) == 1
    assert result.drafts[0].tool_type == "gasto"
    assert result.drafts[0].values == {"concepto": "Papeleria", "monto": 25000.0}

    # Una escritura NUNCA llama a la app antes de que el borrador se confirme.
    assert httpx_mock.get_requests() == []


async def test_invalid_tool_arguments_are_reported_back_to_the_model_not_raised(session, httpx_mock):
    provider = ScriptedProvider(
        [
            ChatResult(
                text=None,
                tool_calls=[ToolCall(id="call_1", name="crear_gasto", arguments={"monto": 100})],  # falta 'concepto'
                model="scripted-model",
            ),
            ChatResult(text="Me falto el concepto del gasto, ¿cual es?", model="scripted-model"),
        ]
    )

    orchestrator = ChatOrchestrator(
        repository=ConversationRepository(session),
        provider_registry=FixedProviderRegistry(provider),
        model_router=ModelRouter(),
    )

    result = await orchestrator.send_message(
        app_identity=APP,
        app_display_name="Nexolu POS",
        tool_registry=build_tool_registry(),
        agent=build_agent_registry().get("cajero"),
        context=ADMIN_CONTEXT,
        message="Registra un gasto de 100",
        conversation_id=None,
    )

    assert "concepto" in result.text
    assert result.drafts == []
    # El segundo turno enviado al proveedor debe llevar el error como
    # resultado de herramienta, no una excepcion que tumbe la conversacion.
    second_call = provider.calls[1]
    tool_turn = next(t for t in second_call.messages if t.tool_call_id == "call_1")
    assert "Falta el parametro obligatorio" in tool_turn.content


async def test_conversation_history_round_trips_across_two_messages(session, httpx_mock):
    provider = ScriptedProvider(
        [
            ChatResult(text="Hola! ¿En que te ayudo?", model="scripted-model"),
            ChatResult(text="Todo tranquilo por ahora.", model="scripted-model"),
        ]
    )

    orchestrator = ChatOrchestrator(
        repository=ConversationRepository(session),
        provider_registry=FixedProviderRegistry(provider),
        model_router=ModelRouter(),
    )

    first = await orchestrator.send_message(
        app_identity=APP,
        app_display_name="Nexolu POS",
        tool_registry=build_tool_registry(),
        agent=build_agent_registry().get("cajero"),
        context=ADMIN_CONTEXT,
        message="Hola",
        conversation_id=None,
    )

    second = await orchestrator.send_message(
        app_identity=APP,
        app_display_name="Nexolu POS",
        tool_registry=build_tool_registry(),
        agent=build_agent_registry().get("cajero"),
        context=ADMIN_CONTEXT,
        message="Como va todo?",
        conversation_id=first.conversation_id,
    )

    assert second.conversation_id == first.conversation_id
    # El segundo request al proveedor debe incluir el turno anterior completo.
    second_request = provider.calls[1]
    contents = [t.content for t in second_request.messages if t.content]
    assert any("Hola" in c for c in contents)
    assert any("Hola! ¿En que te ayudo?" in c for c in contents)
