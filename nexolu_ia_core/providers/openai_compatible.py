"""Base compartida para proveedores que hablan el formato OpenAI `chat/completions`.

OpenRouter, OpenAI y DeepSeek son, a efectos de este payload, el mismo
proveedor con distinta URL, distinta API key y distinta tarifa. Escribir esa
logica tres veces invita a que un fix (el manejo de `arguments` como string
JSON, por ejemplo) se aplique en dos de los tres y no en el tercero.

Puerto directo de `App\\Services\\Ai\\Providers\\OpenRouterProvider::buildMessages/parse`.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from nexolu_ia_core.core.schemas import ChatRequest, ChatResult, ChatStreamEvent, Role, ToolCall
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.exceptions import AiProviderError, AiProviderRetryableError

# 429 (rate limit) y 5xx son transitorios: vale la pena reintentar con
# backoff. 400/401/403/404 son errores de cliente -- reintentarlos no cambia
# el resultado, solo demora el error (ver AiProviderRetryableError).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_retry_on_transient = retry(
    retry=retry_if_exception_type(AiProviderRetryableError),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    reraise=True,
)


class OpenAICompatibleProvider(ChatProvider):
    """Driver generico para APIs OpenAI-compatibles (`/chat/completions`)."""

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        model: str,
        price_input_per_mtok: float,
        price_output_per_mtok: float,
        timeout_seconds: int = 60,
        fallback_models: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_payload: dict | None = None,
    ) -> None:
        if not api_key:
            raise AiProviderError(f"Falta la API key de {provider_name}.")

        self._provider_name = provider_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._price_input = price_input_per_mtok
        self._price_output = price_output_per_mtok
        self._timeout = timeout_seconds
        self._fallback_models = fallback_models or []
        self._extra_headers = extra_headers or {}
        # Payload extra fusionado tal cual en el body (p.ej. {"provider": {...}}
        # de ruteo avanzado de OpenRouter). Generico a proposito: este driver
        # no sabe ni le importa que claves trae, solo las reenvia.
        self._extra_payload = extra_payload or {}

    def name(self) -> str:
        return self._provider_name

    def model(self) -> str:
        return self._model

    def supports_streaming(self) -> bool:
        return True

    async def chat(self, request: ChatRequest) -> ChatResult:
        payload = self._build_payload(request)
        headers = self._build_headers()

        data = await self._post(payload, headers)
        return self._parse(data)

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        payload = self._build_payload(request)
        payload["stream"] = True
        headers = self._build_headers()

        async for event in self._post_stream(payload, headers):
            yield event

    def estimate_cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        input_cost = (input_tokens / 1_000_000) * self._price_input
        output_cost = (output_tokens / 1_000_000) * self._price_output
        return round((input_cost + output_cost) * 1_000_000)

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

    def _build_payload(self, request: ChatRequest) -> dict:
        payload: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": self._build_messages(request),
            # Sin esto la respuesta no trae detalle de tokens cacheados: no hay
            # forma de saber cuanto del prefijo se sirvio desde cache.
            "usage": {"include": True},
        }

        if not request.reasoning:
            payload["reasoning"] = {"enabled": False}

        # Con respaldos configurados se manda el array 'models': el proveedor
        # recorre la lista en orden si el primero falla. El modelo principal
        # va primero para que nada cambie mientras responda bien.
        if self._fallback_models:
            payload["models"] = [self._model, *self._fallback_models]

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]

        payload.update(self._extra_payload)
        return payload

    @_retry_on_transient
    async def _post(self, payload: dict, headers: dict[str, str]) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)

        self._raise_for_status(response.status_code, response.text)
        return response.json()

    async def _post_stream(self, payload: dict, headers: dict[str, str]) -> AsyncIterator[ChatStreamEvent]:
        # `tenacity.retry` no envuelve generadores async (llamar la funcion no
        # ejecuta nada hasta iterarla, asi que no hay excepcion que atrapar):
        # el backoff exponencial se hace a mano aca, con los mismos parametros
        # que `_retry_on_transient` (multiplier=1, min=2, max=10, 4 intentos).
        # Solo reintenta si el fallo ocurre ANTES de emitir el primer delta:
        # una vez que el cliente ya recibio texto, reintentar duplicaria esos
        # tokens en vez de completarlos.
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            started_streaming = False
            try:
                async with (
                    httpx.AsyncClient(timeout=self._timeout) as client,
                    client.stream(
                        "POST", f"{self._base_url}/chat/completions", json=payload, headers=headers
                    ) as response,
                ):
                    if response.status_code >= 400:
                        body = await response.aread()
                        self._raise_for_status(response.status_code, body.decode(errors="replace"))

                    async for event in self._consume_sse(response):
                        started_streaming = True
                        yield event
                return
            except AiProviderRetryableError:
                if started_streaming or attempt == max_attempts:
                    raise
                await asyncio.sleep(min(10, max(2, 2 ** (attempt - 1))))

    def _raise_for_status(self, status_code: int, body: str) -> None:
        if status_code < 400:
            return

        message = f"{self._provider_name} respondio {status_code}: {body}"
        if status_code in _RETRYABLE_STATUS:
            raise AiProviderRetryableError(message)
        raise AiProviderError(message)

    async def _consume_sse(self, response: httpx.Response) -> AsyncIterator[ChatStreamEvent]:
        text_parts: list[str] = []
        tool_call_acc: dict[int, dict] = {}
        model_seen = self._model
        stop_reason: str | None = None
        usage: dict = {}

        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue

            raw = line[len("data:") :].strip()
            if raw == "[DONE]":
                break

            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue

            model_seen = chunk.get("model", model_seen)
            if chunk.get("usage"):
                usage = chunk["usage"]

            choices = chunk.get("choices") or []
            if not choices:
                continue

            choice = choices[0]
            stop_reason = choice.get("finish_reason") or stop_reason
            delta = choice.get("delta") or {}

            content = delta.get("content")
            if content:
                text_parts.append(content)
                yield ChatStreamEvent(delta=content)

            for tc in delta.get("tool_calls") or []:
                index = tc.get("index", 0)
                acc = tool_call_acc.setdefault(index, {"id": None, "name": "", "arguments": ""})
                if tc.get("id"):
                    acc["id"] = tc["id"]
                function = tc.get("function") or {}
                if function.get("name"):
                    acc["name"] += function["name"]
                if function.get("arguments"):
                    acc["arguments"] += function["arguments"]

        tool_calls = self._decode_tool_calls(tool_call_acc)
        cost = usage.get("cost")

        result = ChatResult(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=str(model_seen),
            stop_reason=stop_reason,
            cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)),
            cost_micros=round(float(cost) * 1_000_000) if cost is not None else None,
        )
        yield ChatStreamEvent(done=True, result=result)

    def _decode_tool_calls(self, tool_call_acc: dict[int, dict]) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for index in sorted(tool_call_acc):
            acc = tool_call_acc[index]
            try:
                arguments = json.loads(acc["arguments"]) if acc["arguments"] else {}
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=acc["id"] or f"call_{index}",
                    name=acc["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return tool_calls

    def _build_messages(self, request: ChatRequest) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": request.system}]

        for turn in request.messages:
            if turn.role == Role.USER:
                messages.append({"role": "user", "content": turn.content or ""})
            elif turn.role == Role.ASSISTANT:
                message: dict = {"role": "assistant", "content": turn.content}
                if turn.tool_calls:
                    message["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                # Los argumentos van como string JSON de un objeto,
                                # nunca de una lista: json.dumps({}) ya produce "{}",
                                # pero si `arguments` llegara vacio como lista este
                                # dict comprehension lo evita desde el origen (ver
                                # ToolCall.arguments: dict, no list).
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in turn.tool_calls
                    ]
                messages.append({k: v for k, v in message.items() if v is not None})
            elif turn.role == Role.TOOL:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": turn.tool_call_id,
                        "name": turn.tool_name,
                        "content": turn.content or "",
                    }
                )
            else:
                raise AiProviderError(f"Rol desconocido: {turn.role}")

        return messages

    def _parse(self, data: dict | None) -> ChatResult:
        data = data or {}
        choice = (data.get("choices") or [{}])[0].get("message")

        if choice is None:
            raise AiProviderError(f"Respuesta de {self._provider_name} sin choices.")

        tool_calls: list[ToolCall] = []
        for index, raw in enumerate(choice.get("tool_calls") or []):
            arguments = raw.get("function", {}).get("arguments", "{}")
            try:
                decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
            except (json.JSONDecodeError, TypeError):
                # JSON malformado del modelo: se degrada a vacio para que
                # ToolGuard emita un error de parametro faltante que el modelo
                # pueda corregir, en vez de tumbar la conversacion entera.
                decoded = {}

            tool_calls.append(
                ToolCall(
                    id=raw.get("id", f"call_{index}"),
                    name=raw.get("function", {}).get("name", ""),
                    arguments=decoded if isinstance(decoded, dict) else {},
                )
            )

        usage = data.get("usage") or {}
        cost = usage.get("cost")

        return ChatResult(
            text=choice.get("content"),
            tool_calls=tool_calls,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=str(data.get("model", self._model)),
            stop_reason=(data.get("choices") or [{}])[0].get("finish_reason"),
            cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)),
            # El costo reportado por el proveedor manda sobre el estimado por
            # tarifa configurada: contempla cache y el modelo real que respondio
            # (que con respaldos puede no ser el pedido).
            cost_micros=round(float(cost) * 1_000_000) if cost is not None else None,
        )
