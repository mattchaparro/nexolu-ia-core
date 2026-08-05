"""Herramientas del sistema de Spa.

Existe para demostrar que el mismo `core/tools` sirve para un producto
distinto al POS sin cambiar una linea del Core: son las herramientas que
lista el pedido original (crear_cita, cancelar_cita, clientes,
disponibilidad, empleados), como metadata pura -- igual que en `apps/pos`,
la ejecucion real queda para cuando el Spa exista y exponga su propio
`/api/ai/tools/invoke`.
"""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        WriteTool(
            name="crear_cita",
            description="Agenda una cita para un cliente. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "cliente": {"type": "string"},
                    "servicio": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "hora": {"type": "string", "description": "HH:MM"},
                    "empleado": {"type": "string"},
                },
                "required": ["cliente", "servicio", "fecha", "hora"],
            },
            required_permission="citas.crear",
            draft_type="cita",
            summarize=lambda values: f"Cita: {values.get('cliente')} - {values.get('servicio')} el {values.get('fecha')} {values.get('hora')}",
        )
    )

    registry.register(
        WriteTool(
            name="cancelar_cita",
            description="Cancela una cita existente. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {"cita_id": {"type": "string"}},
                "required": ["cita_id"],
            },
            required_permission="citas.cancelar",
            draft_type="cancelacion_cita",
            summarize=lambda values: f"Cancelar cita #{values.get('cita_id')}",
        )
    )

    registry.register(
        Tool(
            name="clientes",
            description="Busca clientes del spa por nombre o telefono.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            required_permission="clientes.ver",
        )
    )

    registry.register(
        Tool(
            name="disponibilidad",
            description="Horarios disponibles para un servicio en una fecha dada.",
            parameters={
                "type": "object",
                "properties": {
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "servicio": {"type": "string"},
                },
                "required": ["fecha"],
            },
        )
    )

    registry.register(
        Tool(
            name="empleados",
            description="Listado de empleados del spa y los servicios que prestan.",
            parameters={"type": "object", "properties": {}},
        )
    )

    return registry
