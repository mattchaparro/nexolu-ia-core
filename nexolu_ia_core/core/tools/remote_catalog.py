"""Cache de permisos/features reales de cada aplicacion cliente, consultados
en vivo contra su propio backend (ver App\\Capabilities\\* del lado del POS).

Por que existe: `apps/pos/tools.py` declara `required_permission`/
`required_feature` como constantes Python porque el nombre/descripcion/
schema de cada herramienta SI son decision de este repo (como presentarle la
herramienta al modelo). Pero que permiso o feature la protege es una verdad
de negocio que vive en Laravel (o lo que sea el backend de esa app) y puede
cambiar sin que nadie toque este repo - confiar en un string quemado aca es
la misma clase de bug que ya encontramos una vez (`cash.view` en vez de
`cash_shift.manage`, etc.). Esta cache consulta esa verdad en
`GET {base_url}/api/ai/tools/catalog`, con un TTL generoso (ver
`Settings.tool_catalog_ttl_seconds`, un dia por defecto) para no pegarle al
backend en cada mensaje de chat.

Fallar de forma segura: si la app no responde, se usa la cache anterior
aunque este vencida: y si nunca hubo una cache exitosa (primer arranque sin
red), se dejan los valores por defecto que ya trae cada `Tool` desde
`apps/pos/tools.py` en vez de tumbar el chat.
"""
from __future__ import annotations

import logging
import time

import httpx

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.tools.registry import ToolRegistry

logger = logging.getLogger("nexolu_ia_core.tools.remote_catalog")

CATALOG_PATH = "/api/ai/tools/catalog"

ToolRules = dict[str, str | None]
Catalog = dict[str, ToolRules]


class RemoteToolCatalog:
    def __init__(self, ttl_seconds: int, timeout_seconds: int = 10) -> None:
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[float, Catalog]] = {}

    async def sync(self, registry: ToolRegistry, app: AppIdentity) -> None:
        """Sobreescribe required_permission/required_feature de cada Tool
        registrada con lo que reporte el catalogo de la app, si hay dato
        disponible (fresco o cacheado). Si no hay nada disponible, no toca
        nada: el registry se queda con los defaults declarados en Python."""
        catalog = await self._get(app)
        if not catalog:
            return

        for name, tool in registry.all().items():
            rule = catalog.get(name)
            if rule is None:
                continue
            tool.required_permission = rule.get("required_permission")
            tool.required_feature = rule.get("required_feature")

    async def _get(self, app: AppIdentity) -> Catalog:
        cached = self._cache.get(app.app_id)
        if cached and (time.monotonic() - cached[0]) < self._ttl:
            return cached[1]

        fresh = await self._fetch(app)
        if fresh is not None:
            self._cache[app.app_id] = (time.monotonic(), fresh)
            return fresh

        if cached:
            logger.warning("No se pudo refrescar el catalogo de '%s'; se usa la cache anterior.", app.app_id)
            return cached[1]

        logger.warning(
            "No se pudo obtener el catalogo de '%s' y no hay cache previa; se usan los defaults locales.",
            app.app_id,
        )
        return {}

    async def _fetch(self, app: AppIdentity) -> Catalog | None:
        headers = {"Authorization": f"Bearer {app.api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{app.base_url}{CATALOG_PATH}", headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Error de red consultando el catalogo de '%s': %s", app.app_id, exc)
            return None

        if response.status_code != 200:
            logger.warning("El catalogo de '%s' respondio %s.", app.app_id, response.status_code)
            return None

        try:
            body = response.json()
        except ValueError:
            logger.warning("El catalogo de '%s' no devolvio JSON valido.", app.app_id)
            return None

        tools = body.get("tools")
        return tools if isinstance(tools, dict) else None


_instance: RemoteToolCatalog | None = None


def get_remote_tool_catalog() -> RemoteToolCatalog:
    global _instance
    if _instance is None:
        from nexolu_ia_core.config import get_settings

        _instance = RemoteToolCatalog(ttl_seconds=get_settings().tool_catalog_ttl_seconds)
    return _instance
