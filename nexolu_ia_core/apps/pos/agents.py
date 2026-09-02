from __future__ import annotations

from nexolu_ia_core.apps.pos import prompts
from nexolu_ia_core.apps.pos.tools import build_tool_registry
from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.agents.registry import AgentRegistry


def build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()

    # El unico que usa la app. Lleva TODAS las herramientas para que sea el
    # modelo quien elija cual aplica, no el usuario desde un desplegable.
    #
    # La lista se DERIVA del registro de herramientas en vez de escribirse a
    # mano: enumerarla obligaba a acordarse de sumar cada herramienta nueva en
    # dos lados, y olvidarlo no rompe nada visible -- el asistente simplemente
    # dice que no puede hacer algo que la app si sabe hacer. Es exactamente el
    # agujero que hizo inutil al chat del legacy, donde "cuanto vendi en
    # agosto" fallaba porque ventas_resumen vivia en otro agente.
    registry.register(
        AgentDefinition(
            name="asistente",
            display_name="Asistente",
            instructions=prompts.ASISTENTE,
            tool_names=tuple(build_tool_registry().all().keys()),
        )
    )

    # Especializados: se conservan por compatibilidad con clientes que sigan
    # mandando su nombre. No se ofrecen en la interfaz.
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
