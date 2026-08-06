"""Seleccion del modelo/proveedor de IA para un turno de chat.

Precedencia (mas especifico gana): override del agente puntual > override de
la app que llama > default global. El nivel "app" existe para que cada
aplicacion (POS, Spa, EasyTickets...) pueda tener su propio workspace de
proveedor (p.ej. OpenRouter) - modelo distinto, costo y estadisticas
segregados en el dashboard de ese proveedor, sin compartir una sola cuenta.
Ver `AppRegistration.provider/model/provider_api_key` en `config.py`.

`api_key_override` solo se propaga cuando el proveedor RESUELTO coincide con
el `provider` que la app declaro: si un agente puntual fuerza un proveedor
distinto, la API key de la app (pensada para el suyo) no aplica y se cae a
la API key global de ese otro proveedor.

Este es el UNICO lugar que decide que proveedor se usa, para que mañana se
pueda enrutar por costo, por longitud del mensaje, o por disponibilidad
(failover entre proveedores) sin tocar `core/chat/orchestrator.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexolu_ia_core.config import AppRegistration, Settings, get_settings
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str | None = None
    api_key_override: str | None = None


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def resolve(self, agent: AgentDefinition, app: AppIdentity | None = None) -> ModelSelection:
        registration = self._app_registration(app)

        provider = agent.provider or (registration.provider if registration else None) or self._settings.default_provider
        model = agent.model or (registration.model if registration else None)

        api_key_override = None
        if registration and registration.provider_api_key and registration.provider == provider:
            api_key_override = registration.provider_api_key

        return ModelSelection(provider=provider, model=model, api_key_override=api_key_override)

    def _app_registration(self, app: AppIdentity | None) -> AppRegistration | None:
        if app is None:
            return None
        return self._settings.apps.get(app.app_id)
