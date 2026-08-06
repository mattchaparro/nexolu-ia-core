from __future__ import annotations

from nexolu_ia_core.apps.pos import prompts
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.agents.registry import AgentRegistry


def build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()

    registry.register(
        AgentDefinition(
            name="cajero",
            display_name="Cajero",
            instructions=prompts.CAJERO,
            tool_names=("estado_caja", "crear_gasto", "crear_cliente"),
        )
    )

    registry.register(
        AgentDefinition(
            name="analista",
            display_name="Analista",
            instructions=prompts.ANALISTA,
            tool_names=("ventas_resumen", "ventas_por_dia"),
        )
    )

    registry.register(
        AgentDefinition(
            name="inventario",
            display_name="Inventario",
            instructions=prompts.INVENTARIO,
            tool_names=("inventario", "stock_producto", "crear_producto"),
        )
    )

    registry.register(
        AgentDefinition(
            name="restaurante",
            display_name="Restaurante",
            instructions=prompts.RESTAURANTE,
            tool_names=("estado_caja", "crear_gasto", "inventario", "stock_producto"),
        )
    )

    return registry
