from __future__ import annotations

import json

import pytest

from nexolu_ia_core.config import Settings
from nexolu_ia_core.core.schemas import ChatRequest, ChatTurn, ToolCall, ToolDefinition
from nexolu_ia_core.providers.exceptions import AiProviderError
from nexolu_ia_core.providers.openrouter import OpenRouterProvider


def make_settings(**overrides) -> Settings:
    defaults = {
        "openrouter_api_key": "test-key",
        "openrouter_base_url": "https://openrouter.test/api/v1",
        "openrouter_model": "test/model",
        "openrouter_fallback_models": "",
        "openrouter_price_input_per_mtok": 1.0,
        "openrouter_price_output_per_mtok": 2.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_missing_api_key_raises():
    with pytest.raises(AiProviderError):
        OpenRouterProvider(make_settings(openrouter_api_key=""))


async def test_chat_sends_expected_payload_and_parses_response(httpx_mock):
    provider = OpenRouterProvider(make_settings(openrouter_fallback_models="fallback/a,fallback/b"))

    httpx_mock.add_response(
        url="https://openrouter.test/api/v1/chat/completions",
        json={
            "model": "test/model",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"id": "call_1", "function": {"name": "ventas_resumen", "arguments": "{}"}}
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "cost": 0.0005,
                "prompt_tokens_details": {"cached_tokens": 40},
            },
        },
    )

    result = await provider.chat(
        ChatRequest(
            system="eres un asistente",
            messages=[ChatTurn.user("hola")],
            tools=[ToolDefinition(name="ventas_resumen", description="d", parameters={"type": "object"})],
            max_tokens=500,
        )
    )

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)

    assert body["models"] == ["test/model", "fallback/a", "fallback/b"]
    assert body["tools"][0]["function"]["name"] == "ventas_resumen"
    assert body["reasoning"] == {"enabled": False}
    assert request.headers["Authorization"] == "Bearer test-key"

    assert result.wants_tools()
    assert result.tool_calls[0].name == "ventas_resumen"
    assert result.tool_calls[0].arguments == {}
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cached_tokens == 40
    assert result.cost_micros == 500  # 0.0005 USD * 1_000_000


async def test_empty_tool_arguments_serialize_as_json_object(httpx_mock):
    """Un dict vacio debe viajar como '{}', nunca como '[]': un modelo que
    invoca una herramienta sin argumentos no puede romper el turno siguiente
    cuando ese historial se le reenvia al proveedor."""
    provider = OpenRouterProvider(make_settings())

    httpx_mock.add_response(
        url="https://openrouter.test/api/v1/chat/completions",
        json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}},
    )

    await provider.chat(
        ChatRequest(
            system="s",
            messages=[
                ChatTurn.assistant(None, [ToolCall(id="call_1", name="estado_caja", arguments={})]),
                ChatTurn.tool_result("call_1", "estado_caja", "{}"),
            ],
            tools=[],
        )
    )

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assistant_message = body["messages"][1]
    assert assistant_message["tool_calls"][0]["function"]["arguments"] == "{}"


async def test_client_error_raises_immediately_without_retrying(httpx_mock):
    """400/401/403/404 son errores de cliente: reintentarlos no cambia el
    resultado, solo demora el error (ver AiProviderRetryableError)."""
    provider = OpenRouterProvider(make_settings())
    httpx_mock.add_response(status_code=400, text="bad request")

    with pytest.raises(AiProviderError):
        await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    assert len(httpx_mock.get_requests()) == 1


async def test_retryable_status_retries_with_backoff_then_succeeds(httpx_mock):
    """429/5xx son transitorios: se reintentan con backoff exponencial
    (tenacity) antes de rendirse."""
    provider = OpenRouterProvider(make_settings())
    httpx_mock.add_response(status_code=429, text="rate limited")
    httpx_mock.add_response(
        json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}}
    )

    result = await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    assert result.text == "ok"
    assert len(httpx_mock.get_requests()) == 2


async def test_retryable_status_gives_up_after_max_attempts(httpx_mock):
    provider = OpenRouterProvider(make_settings())
    for _ in range(4):
        httpx_mock.add_response(status_code=503, text="unavailable")

    with pytest.raises(AiProviderError):
        await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    assert len(httpx_mock.get_requests()) == 4


async def test_app_site_url_and_site_name_override_the_default_headers(httpx_mock):
    """Cada app registrada puede declarar su propio site_url/site_name (ver
    AppRegistration): OpenRouter los usa para distinguir su trafico en el
    dashboard aunque compartan API key."""
    provider = OpenRouterProvider(
        make_settings(),
        site_url_override="https://pos.nexolu.co",
        site_name_override="Nexolu POS",
    )
    httpx_mock.add_response(
        json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}}
    )

    await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    request = httpx_mock.get_requests()[0]
    assert request.headers["HTTP-Referer"] == "https://pos.nexolu.co"
    assert request.headers["X-Title"] == "Nexolu POS"


async def test_provider_preferences_are_injected_into_the_payload(httpx_mock):
    provider = OpenRouterProvider(
        make_settings(),
        provider_preferences={"order": ["Anthropic", "OpenAI"], "allow_fallbacks": True, "data_collection": "deny"},
    )
    httpx_mock.add_response(
        json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}}
    )

    await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["provider"] == {"order": ["Anthropic", "OpenAI"], "allow_fallbacks": True, "data_collection": "deny"}


async def test_chat_stream_yields_text_deltas_and_a_final_result(httpx_mock):
    provider = OpenRouterProvider(make_settings())
    sse_body = (
        b'data: {"model":"test/model","choices":[{"delta":{"content":"Hola"},"finish_reason":null}]}\n\n'
        b'data: {"model":"test/model","choices":[{"delta":{"content":" mundo"},"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n'
        b'data: [DONE]\n\n'
    )
    httpx_mock.add_response(content=sse_body, headers={"Content-Type": "text/event-stream"})

    events = [event async for event in provider.chat_stream(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))]

    deltas = [e.delta for e in events if e.delta]
    assert deltas == ["Hola", " mundo"]

    final = events[-1]
    assert final.done is True
    assert final.result.text == "Hola mundo"
    assert final.result.input_tokens == 10
    assert final.result.output_tokens == 2


async def test_api_key_override_is_used_instead_of_the_global_settings_key(httpx_mock):
    """El workspace de OpenRouter de una app puntual (ver
    AppRegistration.provider_api_key) tiene que pisar la key global - asi el
    costo/uso queda en el dashboard de esa app, no en la cuenta compartida."""
    provider = OpenRouterProvider(make_settings(), api_key_override="sk-or-app-especifica")

    httpx_mock.add_response(
        url="https://openrouter.test/api/v1/chat/completions",
        json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}},
    )

    await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer sk-or-app-especifica"


async def test_la_temperatura_va_en_cero_salvo_que_se_pida_otra(httpx_mock):
    """Sin fijarla, el proveedor usa la suya (~1.0) y el agente decide
    distinto en cada corrida con la misma conversacion: la evaluacion del
    spa daba 23, 24, 25 y 26 de 28 sin tocar codigo. Esto no escribe
    poesia, decide si mira la agenda o pregunta."""
    provider = OpenRouterProvider(make_settings())
    httpx_mock.add_response(json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}})

    await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))

    assert httpx_mock.get_requests()[0].read()
    import json as _json

    assert _json.loads(httpx_mock.get_requests()[0].read())["temperature"] == 0.0


async def test_se_puede_pedir_otra_temperatura_cuando_hace_falta(httpx_mock):
    """Redactar una campana no es lo mismo que agendar: el cero es el
    valor por defecto, no una prohibicion."""
    provider = OpenRouterProvider(make_settings())
    httpx_mock.add_response(json={"model": "test/model", "choices": [{"message": {"content": "ok"}}], "usage": {}})

    await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")], temperature=0.8))

    import json as _json

    assert _json.loads(httpx_mock.get_requests()[0].read())["temperature"] == 0.8
