"""Identidad de las aplicaciones cliente (POS, Spa, EasyTickets...).

El Core no tiene usuarios ni tenants propios: sus unicos "clientes
autenticados" son las aplicaciones que lo llaman. Cada una tiene una API key
y una `base_url` a la que el Core le devuelve la llamada para ejecutar
herramientas (ver `core/tools/dispatch_client.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

from nexolu_ia_core.config import Settings, get_settings


@dataclass(frozen=True)
class AppIdentity:
    app_id: str
    api_key: str
    base_url: str
    name: str


class AppRegistry:
    """Resuelve una API key a la identidad de la app que la presento."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._by_api_key: dict[str, AppIdentity] = {}

        for app_id, registration in settings.apps.items():
            identity = AppIdentity(
                app_id=app_id,
                api_key=registration.api_key,
                base_url=registration.base_url,
                name=registration.name or app_id,
            )
            self._by_api_key[registration.api_key] = identity

    def resolve_by_api_key(self, api_key: str) -> AppIdentity | None:
        return self._by_api_key.get(api_key)


_registry: AppRegistry | None = None


def get_app_registry() -> AppRegistry:
    global _registry
    if _registry is None:
        _registry = AppRegistry()
    return _registry
