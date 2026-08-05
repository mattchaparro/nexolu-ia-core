from __future__ import annotations

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.agents.registry import AgentRegistry


def build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()

    registry.register(
        AgentDefinition(
            name="recepcionista",
            display_name="Recepcionista",
            instructions=(
                "Atiendes la recepcion del spa: agendas, cancelas y consultas "
                "de clientes. Confirma siempre fecha y hora antes de agendar."
            ),
            tool_names=("crear_cita", "cancelar_cita", "clientes", "disponibilidad"),
        )
    )

    registry.register(
        AgentDefinition(
            name="agenda",
            display_name="Agenda",
            instructions=(
                "Ayudas a organizar la agenda del spa: disponibilidad de "
                "empleados y horarios."
            ),
            tool_names=("disponibilidad", "empleados", "crear_cita"),
        )
    )

    registry.register(
        AgentDefinition(
            name="marketing",
            display_name="Marketing",
            instructions=(
                "Ayudas a identificar clientes para campanas (frecuencia, "
                "servicios preferidos). No agendas ni cancelas nada."
            ),
            tool_names=("clientes",),
        )
    )

    return registry
