"""OpenRouter: pasarela OpenAI-compatible a DeepSeek, Gemini, GPT, Llama, etc.

Advertencia heredada del driver original en el POS: NO todos los modelos
disponibles en OpenRouter soportan function calling, y entre los que si, la
fiabilidad varia. Un modelo que no lo soporta no falla con un error claro:
ignora las tools y responde en prosa inventando datos. Vigilar
`ChatResult.wants_tools()` == False junto con herramientas disponibles es
responsabilidad del orquestador, no de este driver.
"""
from __future__ import annotations

from nexolu_ia_core.config import Settings
from nexolu_ia_core.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        settings: Settings,
        model_override: str | None = None,
        api_key_override: str | None = None,
        site_url_override: str | None = None,
        site_name_override: str | None = None,
        provider_preferences: dict | None = None,
    ) -> None:
        super().__init__(
            provider_name="openrouter",
            # api_key_override: workspace de OpenRouter propio de la app que
            # llama (ver AppRegistration.provider_api_key), para que costos y
            # modelos disponibles queden segregados por app en OpenRouter en
            # vez de compartir una sola cuenta.
            api_key=api_key_override or settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=model_override or settings.openrouter_model,
            price_input_per_mtok=settings.openrouter_price_input_per_mtok,
            price_output_per_mtok=settings.openrouter_price_output_per_mtok,
            timeout_seconds=settings.ai_timeout_seconds,
            fallback_models=settings.openrouter_fallback_models_list,
            # OpenRouter identifica la app que origina el trafico con estos
            # headers. Si la app registrada declaro su propio site_url/
            # site_name (ver AppRegistration), se usan esos en vez del
            # default global -- asi el dashboard de OpenRouter distingue
            # trafico del POS del de EasyTickets aunque compartan API key.
            extra_headers={
                "HTTP-Referer": site_url_override or settings.openrouter_referer,
                "X-Title": site_name_override or settings.openrouter_title,
            },
            # Ruteo avanzado (order, allow_fallbacks, data_collection...)
            # declarado por la app en AppRegistration.provider_preferences.
            # Ver docs de OpenRouter: https://openrouter.ai/docs/quickstart
            extra_payload={"provider": provider_preferences} if provider_preferences else None,
        )
