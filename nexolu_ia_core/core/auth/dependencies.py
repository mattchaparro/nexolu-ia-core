"""Dependencias de FastAPI para autenticar aplicaciones cliente.

El Core no tiene sesion de usuario final: su unico sujeto autenticado es la
APLICACION que llama (POS, Spa, EasyTickets), via API key en el header
`Authorization`. Quien es el usuario final dentro de esa app viaja en el
`TenantContext` del body, y se confia en el precisamente porque la llamada
completa ya esta autenticada por la API key de la app.

Hay un segundo nivel de auth, separado: la API key de PLATAFORMA (Nexolu,
no una app individual), que protege endpoints de reporte cross-app y de
administracion de apps (ver `require_platform_access`, GET /v1/platform/usage
y /v1/admin/apps). Ninguna app integradora la conoce.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.config import get_settings
from nexolu_ia_core.core.auth.apps import AppIdentity, resolve_by_api_key
from nexolu_ia_core.core.memory.db import get_session


async def get_current_app(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AppIdentity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta el header Authorization.")

    api_key = authorization.split(" ", 1)[1].strip()
    app = await resolve_by_api_key(session, api_key)

    if app is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key invalida.")

    return app


async def require_platform_access(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()

    if not settings.nexolu_platform_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El acceso de plataforma no esta configurado (falta NEXOLU_PLATFORM_API_KEY).",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta el header Authorization.")

    api_key = authorization.split(" ", 1)[1].strip()

    # Comparacion de tiempo constante: esta key da acceso a costos de TODAS
    # las apps, vale la pena cerrar el timing side-channel aunque el resto
    # del Core no lo haga sistematicamente.
    if not hmac.compare_digest(api_key, settings.nexolu_platform_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key de plataforma invalida.")
