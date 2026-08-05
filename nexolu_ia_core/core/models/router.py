"""Seleccion del modelo/proveedor de IA para un turno de chat.

Hoy la regla es simple (override del agente > default global), a proposito:
todavia no hay datos de costo/latencia por agente para justificar un ruteo
mas inteligente. El punto de extension ya existe -- este es el UNICO lugar
que decide que proveedor se usa -- para que mañana se pueda enrutar por
costo, por longitud del mensaje, o por disponibilidad (failover entre
proveedores) sin tocar `core/chat/orchestrator.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexolu_ia_core.config import Settings, get_settings
from nexolu_ia_core.core.agents.base import AgentDefinition


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str | None = None


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def resolve(self, agent: AgentDefinition) -> ModelSelection:
        provider = agent.provider or self._settings.default_provider
        model = agent.model
        return ModelSelection(provider=provider, model=model)
