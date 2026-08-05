"""Unico canal por el que el Core le pide a una aplicacion que ejecute algo.

No hay una ruta HTTP por herramienta. Cada aplicacion implementa un solo
endpoint de despacho que recibe `{tool, arguments, context}` y devuelve
`{"data": {...}}` o `{"error": "..."}`. Esto es deliberado: 30 herramientas
en el POS deben significar 30 entradas de registro en Python, no 30 rutas
Laravel nuevas.
"""
from __future__ import annotations

import httpx

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.schemas import TenantContext


class ToolDispatchError(RuntimeError):
    """La aplicacion rechazo o fallo al ejecutar la herramienta."""


class AppToolClient:
    DISPATCH_PATH = "/api/ai/tools/invoke"

    def __init__(self, app: AppIdentity, timeout_seconds: int = 30) -> None:
        self._app = app
        self._timeout = timeout_seconds

    async def invoke(self, tool_name: str, arguments: dict, context: TenantContext) -> dict:
        payload = {
            "tool": tool_name,
            "arguments": arguments,
            "context": context.model_dump(),
        }
        headers = {"Authorization": f"Bearer {self._app.api_key}"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{self._app.base_url}{self.DISPATCH_PATH}", json=payload, headers=headers
                )
            except httpx.HTTPError as exc:
                raise ToolDispatchError(
                    f"No se pudo contactar a {self._app.name} para ejecutar '{tool_name}': {exc}"
                ) from exc

        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.status_code >= 400 or "error" in body:
            message = body.get("error") or f"{self._app.name} respondio {response.status_code}"
            raise ToolDispatchError(message)

        return body.get("data", {})
