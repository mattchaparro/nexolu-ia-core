"""Proveedor determinista para tests y entornos sin API keys configuradas.

Nunca llama nada por red. Sirve para probar el orquestador de chat
(historial, loop de herramientas, persistencia) sin gastar tokens reales ni
depender de que un proveedor externo este arriba.
"""
from __future__ import annotations

from nexolu_ia_core.core.schemas import ChatRequest, ChatResult
from nexolu_ia_core.providers.base import ChatProvider


class NullProvider(ChatProvider):
    def name(self) -> str:
        return "null"

    def model(self) -> str:
        return "null"

    async def chat(self, request: ChatRequest) -> ChatResult:
        last_user = next(
            (t for t in reversed(request.messages) if t.role.value == "user"), None
        )
        text = f"[null] recibido: {last_user.content}" if last_user else "[null] sin mensaje de usuario."

        return ChatResult(
            text=text,
            tool_calls=[],
            input_tokens=0,
            output_tokens=0,
            model="null",
            stop_reason="stop",
        )

    def estimate_cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        return 0
