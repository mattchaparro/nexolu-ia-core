from __future__ import annotations

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.agents.registry import AgentRegistry


def build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()

    registry.register(
        AgentDefinition(
            name="soporte",
            display_name="Soporte",
            instructions="Ayudas a asistentes a validar y consultar tickets en la puerta del evento.",
            tool_names=("consultar_ticket", "validar_qr"),
        )
    )

    registry.register(
        AgentDefinition(
            name="eventos",
            display_name="Eventos",
            instructions="Ayudas a organizadores a crear y revisar eventos.",
            tool_names=("crear_evento", "consultar_ticket"),
        )
    )

    registry.register(
        AgentDefinition(
            name="ventas",
            display_name="Ventas",
            instructions="Ayudas a vender tickets y confirmar el estado de una compra.",
            tool_names=("vender_ticket", "consultar_ticket"),
        )
    )

    return registry
