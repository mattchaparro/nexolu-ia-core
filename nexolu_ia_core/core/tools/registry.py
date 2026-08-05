"""Whitelist de herramientas de una aplicacion.

Si una herramienta no esta registrada aca, no existe para el modelo, y un
intento de invocarla por nombre termina en `ToolNotAllowedException` en vez
de en una resolucion dinamica. Equivale a
`App\\Services\\Ai\\ToolRegistry` en el POS, pero instanciado una vez por
aplicacion (POS, Spa, EasyTickets), no de forma global: las herramientas de
un producto nunca son visibles para otro.
"""
from __future__ import annotations

import re

from nexolu_ia_core.core.schemas import TenantContext
from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.exceptions import ToolNotAllowedException

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not _NAME_RE.match(tool.name):
            raise ValueError(f"Nombre de herramienta invalido: {tool.name}")
        if tool.name in self._tools:
            raise ValueError(f"Herramienta duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def available_for(self, context: TenantContext) -> dict[str, Tool]:
        """Herramientas visibles para el tenant dado.

        Se cruzan dos filtros y hay que pasar los dos: `required_feature`
        (el negocio contrato el modulo) y `required_permission` (el usuario
        puede verlo en la interfaz). El administrador del tenant pasa el
        filtro de permiso sin evaluarlo -- igual que el dueno del negocio en
        el POS --, pero el de feature se aplica siempre.
        """
        result: dict[str, Tool] = {}

        for name, tool in self._tools.items():
            if tool.required_feature is not None and tool.required_feature not in context.features:
                continue

            if (
                not context.is_admin
                and tool.required_permission is not None
                and tool.required_permission not in context.permissions
            ):
                continue

            result[name] = tool

        return result

    def resolve_for(self, context: TenantContext, name: str) -> Tool:
        """Resuelve una herramienta por nombre verificando que el tenant pueda usarla.

        El chequeo se repite aca a proposito: no basta con no ofrecer la
        herramienta en la lista enviada al proveedor. Un modelo puede
        inventar un nombre que no se le paso, y ese camino tiene que morir
        aca y no en la ejecucion.
        """
        available = self.available_for(context)
        tool = available.get(name)
        if tool is None:
            raise ToolNotAllowedException(
                f"La herramienta '{name}' no existe o no esta habilitada para este contexto."
            )
        return tool

    def write_tool_for_draft_type(self, context: TenantContext, draft_type: str) -> WriteTool:
        for tool in self.available_for(context).values():
            if isinstance(tool, WriteTool) and tool.draft_type == draft_type:
                return tool
        raise ToolNotAllowedException(
            f"No hay ninguna herramienta habilitada para confirmar un borrador de tipo '{draft_type}'."
        )

    def all(self) -> dict[str, Tool]:
        return dict(self._tools)
