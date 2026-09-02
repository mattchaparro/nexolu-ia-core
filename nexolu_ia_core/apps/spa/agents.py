"""Agentes del Spa.

UNO solo, y a proposito: quien escribe por WhatsApp es una CLIENTA, no una
empleada eligiendo con que asistente hablar. Elegir el agente no es trabajo
suyo -- ni siquiera sabe que existe la idea.

Los agentes internos (agenda, marketing) volveran cuando el panel del Spa
tenga su propio chat, con las herramientas de empleada que hoy no existen.
Declararlos ahora seria ofrecer roles que apuntan a herramientas que la app
no implementa.
"""
from __future__ import annotations

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.agents.registry import AgentRegistry

INSTRUCCIONES = (
    "Atiendes por WhatsApp a las clientas del negocio y las ayudas a agendar, "
    "consultar o cancelar sus citas. Hablas como la recepcion del local: "
    "cercana, breve y sin rodeos.\n\n"
    "Reglas que no puedes romper:\n"
    "- La disponibilidad sale SOLO de `disponibilidad`, y los precios SOLO de "
    "`servicios`. Nunca supongas que una hora esta libre.\n"
    "- Antes de agendar, repite en una frase servicio, dia, hora y con quien, "
    "y espera a que la persona confirme. Solo entonces llamas a `crear_cita`.\n"
    "- Si la hora que querian ya se ocupo, no te disculpes largo: ofrece dos o "
    "tres alternativas del mismo dia.\n"
    "- Solo puedes ver y tocar las citas de quien te escribe. Si te piden algo "
    "de otra persona, di que no puedes y ofrece que el negocio la contacte.\n"
    "- Si no sabes algo que ninguna herramienta responde -- promociones, "
    "garantias, parqueadero -- dilo y ofrece que alguien del local escriba."
)


def build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()

    registry.register(
        AgentDefinition(
            name="recepcionista",
            display_name="Recepcion",
            instructions=INSTRUCCIONES,
            tool_names=(
                "servicios",
                "disponibilidad",
                "mis_citas",
                "crear_cita",
                "cancelar_cita",
            ),
        )
    )

    return registry
