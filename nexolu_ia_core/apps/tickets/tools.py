"""Herramientas de EasyTickets: mismo patron que apps/pos y apps/spa."""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        WriteTool(
            name="crear_evento",
            description="Crea un evento nuevo. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "lugar": {"type": "string"},
                    "capacidad": {"type": "integer", "minimum": 1},
                },
                "required": ["nombre", "fecha", "lugar"],
            },
            required_permission="eventos.crear",
            draft_type="evento",
            summarize=lambda values: f"Evento: {values.get('nombre')} el {values.get('fecha')} en {values.get('lugar')}",
        )
    )

    registry.register(
        WriteTool(
            name="vender_ticket",
            description="Vende una o mas entradas de un evento. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "evento_id": {"type": "string"},
                    "cliente": {"type": "string"},
                    "cantidad": {"type": "integer", "minimum": 1},
                },
                "required": ["evento_id", "cliente", "cantidad"],
            },
            required_permission="tickets.vender",
            draft_type="venta_ticket",
            summarize=lambda values: f"Venta: {values.get('cantidad')} ticket(s) para {values.get('cliente')}",
        )
    )

    registry.register(
        Tool(
            name="consultar_ticket",
            description="Consulta el estado de un ticket por su identificador.",
            parameters={
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        )
    )

    registry.register(
        Tool(
            name="validar_qr",
            description="Valida el codigo QR de un ticket en la entrada del evento.",
            parameters={
                "type": "object",
                "properties": {"codigo_qr": {"type": "string"}},
                "required": ["codigo_qr"],
            },
            required_permission="tickets.validar",
        )
    )

    return registry
