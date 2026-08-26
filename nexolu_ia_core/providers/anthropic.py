"""Driver nativo para la API de Anthropic (Messages API).

A diferencia del formato OpenAI, Anthropic separa el `system` como parametro
propio (no un mensaje mas) y representa texto/llamadas a herramienta como
bloques dentro de `content`, no como campos planos. Por eso vive aparte de
`OpenAICompatibleProvider` en vez de heredar de ella.
"""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from nexolu_ia_core.config import Settings
from nexolu_ia_core.core.schemas import ChatRequest, ChatResult, Role, ToolCall
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.exceptions import AiProviderError, AiProviderRetryableError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_retry_on_transient = retry(
    retry=retry_if_exception_type(AiProviderRetryableError),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    reraise=True,
)


class AnthropicProvider(ChatProvider):
    def __init__(
        self, settings: Settings, model_override: str | None = None, api_key_override: str | None = None
    ) -> None:
        if not api_key_override and not settings.anthropic_api_key:
            raise AiProviderError("Falta ANTHROPIC_API_KEY.")

        self._api_key = api_key_override or settings.anthropic_api_key
        self._base_url = settings.anthropic_base_url.rstrip("/")
        self._version = settings.anthropic_version
        self._model = model_override or settings.anthropic_model
        self._price_input = settings.anthropic_price_input_per_mtok
        self._price_output = settings.anthropic_price_output_per_mtok
        self._timeout = settings.ai_timeout_seconds

    def name(self) -> str:
        return "anthropic"

    def model(self) -> str:
        return self._model

    async def chat(self, request: ChatRequest) -> ChatResult:
        payload: dict = {
            "model": self._model,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "messages": self._build_messages(request),
        }

        if request.tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in request.tools
            ]

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._version,
            "Content-Type": "application/json",
        }

        data = await self._post(payload, headers)
        return self._parse(data)

    @_retry_on_transient
    async def _post(self, payload: dict, headers: dict[str, str]) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/v1/messages", json=payload, headers=headers)

        if response.status_code >= 400:
            message = f"Anthropic respondio {response.status_code}: {response.text}"
            if response.status_code in _RETRYABLE_STATUS:
                raise AiProviderRetryableError(message)
            raise AiProviderError(message)

        return response.json()

    def estimate_cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        input_cost = (input_tokens / 1_000_000) * self._price_input
        output_cost = (output_tokens / 1_000_000) * self._price_output
        return round((input_cost + output_cost) * 1_000_000)

    def _build_messages(self, request: ChatRequest) -> list[dict]:
        messages: list[dict] = []
        pending_tool_results: list[dict] = []

        def flush_tool_results() -> None:
            if pending_tool_results:
                messages.append({"role": "user", "content": list(pending_tool_results)})
                pending_tool_results.clear()

        for turn in request.messages:
            if turn.role == Role.TOOL:
                # Anthropic exige que TODOS los resultados de un mismo turno de
                # herramientas viajen juntos en un unico mensaje "user": se
                # acumulan y se emiten de una sola vez cuando aparece cualquier
                # otro tipo de turno (ver flush_tool_results).
                pending_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": turn.tool_call_id,
                        "content": turn.content or "",
                    }
                )
                continue

            flush_tool_results()

            if turn.role == Role.USER:
                messages.append({"role": "user", "content": turn.content or ""})
            elif turn.role == Role.ASSISTANT:
                blocks: list[dict] = []
                if turn.content:
                    blocks.append({"type": "text", "text": turn.content})
                for call in turn.tool_calls:
                    blocks.append(
                        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                    )
                messages.append({"role": "assistant", "content": blocks})
            else:
                raise AiProviderError(f"Rol desconocido: {turn.role}")

        flush_tool_results()
        return messages

    def _parse(self, data: dict | None) -> ChatResult:
        data = data or {}
        blocks = data.get("content") or []

        text_parts = [b["text"] for b in blocks if b.get("type") == "text"]
        tool_calls = [
            ToolCall(id=b["id"], name=b["name"], arguments=b.get("input") or {})
            for b in blocks
            if b.get("type") == "tool_use"
        ]

        usage = data.get("usage") or {}

        return ChatResult(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=str(data.get("model", self._model)),
            stop_reason=data.get("stop_reason"),
            cached_tokens=int(usage.get("cache_read_input_tokens", 0)),
            # Anthropic no reporta el costo cobrado en la respuesta (a
            # diferencia de OpenRouter): se deja en None para que el
            # orquestador use `estimate_cost_micros` con la tarifa configurada.
            cost_micros=None,
        )
