"""Dependencias de FastAPI para autenticar aplicaciones cliente.

El Core no tiene sesion de usuario final: su unico sujeto autenticado es la
APLICACION que llama (POS, Spa, EasyTickets), via API key en el header
`Authorization`. Quien es el usuario final dentro de esa app viaja en el
`TenantContext` del body, y se confia en el precisamente porque la llamada
completa ya esta autenticada por la API key de la app.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from nexolu_ia_core.core.auth.apps import AppIdentity, get_app_registry


async def get_current_app(authorization: str | None = Header(default=None)) -> AppIdentity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta el header Authorization.")

    api_key = authorization.split(" ", 1)[1].strip()
    app = get_app_registry().resolve_by_api_key(api_key)

    if app is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key invalida.")

    return app
