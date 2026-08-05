"""Punto unico donde el servicio conoce que aplicaciones existen.

Es la UNICA pieza del Core que sabe que "pos", "spa" y "tickets" son cosas
concretas -- y vive fuera de `core/` a proposito: `core/chat/orchestrator.py`
nunca importa esto ni nada bajo `nexolu_ia_core.apps`. Agregar una aplicacion
nueva (CRM, lo que sea) es agregar una rama aca y un paquete
`apps/<nombre>/` con sus propios `tools.py`/`agents.py`; nada en `core/`
cambia.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexolu_ia_core.core.agents.registry import AgentRegistry
from nexolu_ia_core.core.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AppBundle:
    app_id: str
    display_name: str
    tools: ToolRegistry
    agents: AgentRegistry


def get_app_bundle(app_id: str) -> AppBundle:
    if app_id == "pos":
        from nexolu_ia_core.apps.pos import build_bundle

        return build_bundle()

    if app_id == "spa":
        from nexolu_ia_core.apps.spa import build_bundle

        return build_bundle()

    if app_id == "tickets":
        from nexolu_ia_core.apps.tickets import build_bundle

        return build_bundle()

    raise KeyError(f"Aplicacion desconocida: {app_id}")
