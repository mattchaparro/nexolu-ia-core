"""Fabrica de proveedores segun configuracion.

Agregar un proveedor nuevo (Ollama local, Gemini nativo, lo que sea) es:
1. escribir la clase (heredando de `OpenAICompatibleProvider` si habla ese
   formato, o de `ChatProvider` directo si no),
2. agregar una rama aca.

Nada mas del sistema necesita cambiar: `core/models/router.py` solo pide
proveedores por nombre.
"""
from __future__ import annotations

from functools import lru_cache

from nexolu_ia_core.config import Settings, get_settings
from nexolu_ia_core.providers.anthropic import AnthropicProvider
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.deepseek import DeepSeekProvider
from nexolu_ia_core.providers.exceptions import AiProviderError
from nexolu_ia_core.providers.null import NullProvider
from nexolu_ia_core.providers.openai import OpenAIProvider
from nexolu_ia_core.providers.openrouter import OpenRouterProvider


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def resolve(self, name: str, model_override: str | None = None, api_key_override: str | None = None) -> ChatProvider:
        builders = {
            "openrouter": lambda: OpenRouterProvider(self._settings, model_override, api_key_override),
            "openai": lambda: OpenAIProvider(self._settings, model_override, api_key_override),
            "deepseek": lambda: DeepSeekProvider(self._settings, model_override, api_key_override),
            "anthropic": lambda: AnthropicProvider(self._settings, model_override, api_key_override),
            "null": NullProvider,
        }

        builder = builders.get(name)
        if builder is None:
            raise AiProviderError(f"Proveedor de IA desconocido: {name}")

        return builder()


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry()
