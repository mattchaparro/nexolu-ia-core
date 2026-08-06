"""Configuracion central del servicio.

Todo lo que varia entre entornos (desarrollo, staging, produccion) vive aqui,
leido de variables de entorno. Nada de esto es logica de negocio de ningun
producto: son credenciales de proveedores de IA y el registro de que
aplicaciones (POS, Spa, EasyTickets...) pueden llamar al Core.
"""
from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppRegistration(BaseSettings):
    """Una aplicacion cliente del Core (POS, Spa, EasyTickets...).

    provider/model/provider_api_key son opcionales: una app que no los
    declara usa el default global (DEFAULT_PROVIDER/DEFAULT_MODEL y la API
    key global de ese proveedor). Declararlos es lo que permite que, por
    ejemplo, el POS use un modelo barato con su propio workspace de
    OpenRouter y el Spa use uno mas potente con el suyo - estadisticas,
    costos y acceso a modelos quedan segregados por app en el dashboard del
    proveedor, no mezclados bajo una sola cuenta. Ver ModelRouter.resolve().
    """

    api_key: str
    base_url: str
    name: str = ""
    provider: str | None = None
    model: str | None = None
    provider_api_key: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Persistencia
    database_url: str = Field(default="sqlite+aiosqlite:///./nexolu_ia_core.db")

    # Seleccion de modelo por defecto (ver core/models/router.py)
    default_provider: str = Field(default="null")
    default_model: str = Field(default="null")

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_referer: str = "https://nexolu.co"
    openrouter_title: str = "Nexolu IA Core"
    openrouter_fallback_models: str = ""
    openrouter_price_input_per_mtok: float = 0.30
    openrouter_price_output_per_mtok: float = 1.20

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    openai_price_input_per_mtok: float = 0.40
    openai_price_output_per_mtok: float = 1.60

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_price_input_per_mtok: float = 0.28
    deepseek_price_output_per_mtok: float = 1.10

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    anthropic_model: str = "claude-opus-4-8"
    anthropic_price_input_per_mtok: float = 5.00
    anthropic_price_output_per_mtok: float = 25.00

    # Limites comunes
    ai_timeout_seconds: int = 60
    ai_max_output_tokens: int = 1500
    ai_history_turns: int = 20

    # Registro de apps cliente, como JSON crudo (parseado en `apps`).
    nexolu_apps_json: str = "{}"

    # Cuanto tiempo confiar en el catalogo de permisos/features de una app
    # (ver core/tools/remote_catalog.py) antes de volver a consultarlo. Un
    # dia por defecto: ese dato cambia poco y consultarlo en cada mensaje de
    # chat le pegaria al backend de la app sin necesidad.
    tool_catalog_ttl_seconds: int = Field(default=86400)

    # Credencial de PLATAFORMA (Nexolu, no una app individual): da acceso a
    # GET /v1/platform/usage, que agrega el gasto por app_id de TODAS las
    # apps. Nunca se le entrega a una app integradora - esa usa su propia
    # api_key para ver solo su propio gasto en GET /v1/usage/*. Vacia por
    # defecto: sin ella, /v1/platform/usage responde 503 en vez de quedar
    # accesible sin proteccion. Prefijo NEXOLU_ (no per-app) a proposito,
    # igual que NEXOLU_APPS_JSON.
    nexolu_platform_api_key: str = ""

    log_level: str = "INFO"

    @property
    def apps(self) -> dict[str, AppRegistration]:
        raw = json.loads(self.nexolu_apps_json or "{}")
        return {app_id: AppRegistration(**data) for app_id, data in raw.items()}

    @property
    def openrouter_fallback_models_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
