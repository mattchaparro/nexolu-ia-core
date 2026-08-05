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


async def test_http_error_raises_provider_error(httpx_mock):
    provider = OpenRouterProvider(make_settings())
    httpx_mock.add_response(status_code=500, text="boom")

    with pytest.raises(AiProviderError):
        await provider.chat(ChatRequest(system="s", messages=[ChatTurn.user("hola")]))
