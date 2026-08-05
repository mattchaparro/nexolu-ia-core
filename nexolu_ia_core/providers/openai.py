"""OpenAI nativo, mismo formato `chat/completions` que OpenRouter."""
from __future__ import annotations

from nexolu_ia_core.config import Settings
from nexolu_ia_core.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, settings: Settings, model_override: str | None = None) -> None:
        super().__init__(
            provider_name="openai",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=model_override or settings.openai_model,
            price_input_per_mtok=settings.openai_price_input_per_mtok,
            price_output_per_mtok=settings.openai_price_output_per_mtok,
            timeout_seconds=settings.ai_timeout_seconds,
        )
