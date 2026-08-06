"""Contrato que todo proveedor de IA debe cumplir.

Equivalente a `App\\Services\\Ai\\Contracts\\ChatProvider` en el POS. El
orquestador de chat (`core/chat/orchestrator.py`) solo conoce esta interfaz:
agregar un proveedor nuevo (Ollama local, Gemini nativo, lo que sea) es
escribir una subclase y registrarla en `ProviderRegistry`, sin tocar el
orquestador.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from nexolu_ia_core.core.schemas import ChatRequest, ChatResult


class ChatProvider(ABC):
    @abstractmethod
    def name(self) -> str:
        """Identificador estable del proveedor, p.ej. 'openrouter'."""

    @abstractmethod
    def model(self) -> str:
        """Modelo por defecto configurado para este proveedor."""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResult:
        """Envia la conversacion y devuelve la respuesta normalizada."""

    def estimate_cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        """Costo estimado con tarifas de config. Respaldo si el proveedor no reporta costo real."""
        return 0
