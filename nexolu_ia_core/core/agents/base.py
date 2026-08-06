"""Un agente es una personalidad + un subconjunto de herramientas sobre el
mismo motor de chat.

Todos los agentes de todas las aplicaciones comparten `ChatOrchestrator`,
`ToolGuard`, los proveedores y la memoria: lo unico que varia por agente es
el texto que se le agrega al system prompt y que herramientas se le ofrecen
al modelo. Ver el pedido original: POS tiene Cajero/Analista/Inventario/
Restaurante, Spa tiene Recepcionista/Agenda/Marketing, etc. -- todos "el
mismo motor de IA".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    display_name: str
    instructions: str
    # Nombres de herramientas del ToolRegistry de la app que este agente puede
    # usar. Vacio/None = todas las que el tenant tenga habilitadas.
    tool_names: tuple[str, ...] | None = None
    # Override opcional de proveedor/modelo para este agente puntual (p.ej. un
    # agente de "Analista" que necesita mas razonamiento que el "Cajero").
    provider: str | None = None
    model: str | None = None
