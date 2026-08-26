"""Seleccion del modelo/proveedor de IA para un turno de chat.

Precedencia (mas especifico gana): override del agente puntual > override de
la app que llama > default global. El nivel "app" existe para que cada
aplicacion (POS, Spa, EasyTickets...) pueda tener su propio workspace de
proveedor (p.ej. OpenRouter) - modelo distinto, costo y estadisticas
segregados en el dashboard de ese proveedor, sin compartir una sola cuenta.
Ver `AppRegistration` en `core/memory/entities.py` y `AppIdentity` en
`core/auth/apps.py`, que ya trae estos campos resueltos desde BD.

`api_key_override` solo se propaga cuando el proveedor RESUELTO coincide con
el `provider` que la app declaro: si un agente puntual fuerza un proveedor
distinto, la API key de la app (pensada para el suyo) no aplica y se cae a
la API key global de ese otro proveedor.

Este es el UNICO lugar que decide que proveedor se usa, para que mañana se
pueda enrutar por costo, por longitud del mensaje, o por disponibilidad
(failover entre proveedores) sin tocar `core/chat/orchestrator.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nexolu_ia_core.config import Settings, get_settings
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str | None = None
    api_key_override: str | None = None
    site_url: str | None = None
    site_name: str | None = None
    provider_preferences: dict = field(default_factory=dict)


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def resolve(self, agent: AgentDefinition, app: AppIdentity | None = None) -> ModelSelection:
        provider = agent.provider or (app.provider if app else None) or self._settings.default_provider
        model = agent.model or (app.model if app else None)

        api_key_override = None
        if app and app.provider_api_key and app.provider == provider:
            api_key_override = app.provider_api_key

        return ModelSelection(
            provider=provider,
            model=model,
            api_key_override=api_key_override,
            site_url=app.site_url if app else None,
            site_name=app.site_name if app else None,
            provider_preferences=(app.provider_preferences if app else {}) or {},
        )
