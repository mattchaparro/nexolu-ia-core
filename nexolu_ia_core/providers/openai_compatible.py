"""Base compartida para proveedores que hablan el formato OpenAI `chat/completions`.

OpenRouter, OpenAI y DeepSeek son, a efectos de este payload, el mismo
proveedor con distinta URL, distinta API key y distinta tarifa. Escribir esa
logica tres veces invita a que un fix (el manejo de `arguments` como string
JSON, por ejemplo) se aplique en dos de los tres y no en el tercero.

Puerto directo de `App\\Services\\Ai\\Providers\\OpenRouterProvider::buildMessages/parse`.
"""
from __future__ import annotations

import json

import httpx

from nexolu_ia_core.core.schemas import ChatRequest, ChatResult, Role, ToolCall
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.exceptions import AiProviderError


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

    def name(self) -> str:
        return self._provider_name

    def model(self) -> str:
        return self._model

    async def chat(self, request: ChatRequest) -> ChatResult:
        payload: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
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

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )

        if response.status_code >= 400:
            raise AiProviderError(
                f"{self._provider_name} respondio {response.status_code}: {response.text}"
            )

        return self._parse(response.json())

    def estimate_cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        input_cost = (input_tokens / 1_000_000) * self._price_input
        output_cost = (output_tokens / 1_000_000) * self._price_output
        return round((input_cost + output_cost) * 1_000_000)

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
