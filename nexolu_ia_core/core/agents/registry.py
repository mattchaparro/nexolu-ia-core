from __future__ import annotations

from nexolu_ia_core.core.agents.base import AgentDefinition


class AgentRegistry:
    """Agentes disponibles dentro de UNA aplicacion (POS, Spa, EasyTickets)."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agente duplicado: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentDefinition:
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"Agente desconocido: {name}")
        return agent

    def all(self) -> dict[str, AgentDefinition]:
        return dict(self._agents)
