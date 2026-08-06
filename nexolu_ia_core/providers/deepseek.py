"""DeepSeek nativo: API OpenAI-compatible, sin pasar por OpenRouter."""
from __future__ import annotations

from nexolu_ia_core.config import Settings
from nexolu_ia_core.providers.openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(
        self, settings: Settings, model_override: str | None = None, api_key_override: str | None = None
    ) -> None:
        super().__init__(
            provider_name="deepseek",
            api_key=api_key_override or settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=model_override or settings.deepseek_model,
            price_input_per_mtok=settings.deepseek_price_input_per_mtok,
            price_output_per_mtok=settings.deepseek_price_output_per_mtok,
            timeout_seconds=settings.ai_timeout_seconds,
        )
