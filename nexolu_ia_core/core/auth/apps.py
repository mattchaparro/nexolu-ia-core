"""Identidad de las aplicaciones cliente (POS, Spa, EasyTickets...).

El Core no tiene usuarios ni tenants propios: sus unicos "clientes
autenticados" son las aplicaciones que lo llaman. Cada una tiene una API key
y una `base_url` a la que el Core le devuelve la llamada para ejecutar
herramientas (ver `core/tools/dispatch_client.py`).

La identidad vive en BD (`core.memory.entities.AppRegistration`), no en env
vars: `resolve_by_api_key` consulta por hash y compara en tiempo constante
(`hmac.compare_digest`) contra el hash guardado, para no filtrar por timing
si una key es casi correcta.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.repository import AppRegistrationRepository
from nexolu_ia_core.core.security.api_keys import hash_api_key


@dataclass(frozen=True)
class AppIdentity:
    app_id: str
    api_key: str
    base_url: str
    name: str
    site_url: str | None = None
    site_name: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_api_key: str | None = None
    provider_preferences: dict = field(default_factory=dict)


async def resolve_by_api_key(session: AsyncSession, api_key: str) -> AppIdentity | None:
    """Busca la app activa duena de `api_key`.

    La busqueda en BD ya es por `api_key_hash` (columna indexada y unica), y
    ademas se confirma con `hmac.compare_digest` entre el hash calculado y el
    guardado antes de aceptarla: asi ninguna comparacion de bytes de la key
    real ocurre en tiempo variable en el camino de autenticacion.
    """
    computed_hash = hash_api_key(api_key)
    registration = await AppRegistrationRepository(session).get_active_by_api_key_hash(computed_hash)

    if registration is None:
        return None

    if not hmac.compare_digest(registration.api_key_hash, computed_hash):
        return None

    return AppIdentity(
        app_id=registration.app_id,
        api_key=registration.api_key,
        base_url=registration.base_url,
        name=registration.name or registration.app_id,
        site_url=registration.site_url,
        site_name=registration.site_name,
        provider=registration.provider,
        model=registration.model,
        provider_api_key=registration.provider_api_key,
        provider_preferences=registration.provider_preferences or {},
    )
