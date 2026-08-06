"""Construccion del system prompt.

Se arma en capas -- persona base del Core, instrucciones del agente,
contexto de tenant -- para que cada aplicacion/agente solo aporte lo que le
es propio (Prompt Engineering es una responsabilidad del Core, no algo que
cada app reimplemente).

El contexto de fecha/hora va pegado al ULTIMO turno de usuario en el
orquestador, no aca, por la misma razon que en el POS
(`AiSystemPrompt`/`AiChatService::construirTurnos`): mantiene este prefijo
estable y cacheable entre mensajes de la misma conversacion.
"""
from __future__ import annotations

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.schemas import TenantContext

BASE_PERSONA = (
    "Eres el asistente de inteligencia artificial de Nexolu. Respondes en "
    "espanol, de forma breve y concreta. Solo puedes conocer datos del "
    "negocio a traves de las herramientas que se te ofrecen: nunca inventes "
    "cifras, nombres o resultados que no vengan de una llamada a herramienta. "
    "Si ninguna herramienta disponible sirve para lo que te piden, dilo "
    "claramente en vez de responder de memoria."
)


class SystemPromptBuilder:
    def build(self, *, app_name: str, agent: AgentDefinition, context: TenantContext) -> str:
        parts = [
            BASE_PERSONA,
            f"Aplicacion: {app_name}. Rol: {agent.display_name}.",
            agent.instructions,
        ]
        return "\n\n".join(p for p in parts if p)
