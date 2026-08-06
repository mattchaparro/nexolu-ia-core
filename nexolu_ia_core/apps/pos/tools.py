"""Herramientas del POS, registradas del lado del Core.

Esto es solo metadata: nombre, descripcion, JSON Schema y permisos. La
ejecucion real de cada una viaja por `AppToolClient` hacia
`POST {base_url}/api/ai/tools/invoke` del lado del POS (Laravel) -- ese
endpoint ya existe en el POS real (`App\\Capabilities\\*`, ver
`App\\Http\\Controllers\\Api\\AiToolInvokeController`); apuntar
`base_url` a esa app es toda la migracion necesaria.

Los `name` de cada herramienta son el contrato compartido con
`App\\Capabilities\\Registry::MAP` del lado del POS y viajan en español
a proposito (son datos, no codigo: el catalogo que ve el modelo). Las
clases que las implementan del lado del POS estan en ingles porque ahi
aplica la convencion de codigo del proyecto, pero el string por el que se
invocan es el mismo en los dos lados. `required_permission` y
`required_feature`, en cambio, tienen que calzar EXACTO con los nombres
reales de `App\\Support\\PermissionCatalog` y `feature_flags` de Laravel
- son claves de otro sistema, no vocabulario propio: un typo aca no rompe
nada en este repo (los tests locales no lo detectan), pero silenciosamente
esconde o expone mal una herramienta del lado del POS.

Las herramientas de escritura (`crear_gasto`, `crear_producto`,
`crear_cliente`) nunca ejecutan de inmediato: generan un borrador que el
usuario confirma explicitamente (ver `core/tools/base.py::WriteTool`).
"""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="ventas_resumen",
            description="Resumen de ventas del negocio en un rango de fechas: total, numero de ventas, ticket promedio.",
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                },
            },
            required_permission="reports.sales",
        )
    )

    registry.register(
        Tool(
            name="ventas_por_dia",
            description="Serie diaria de ventas dentro de un rango de fechas.",
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                },
                "required": ["desde", "hasta"],
            },
            required_permission="reports.sales",
        )
    )

    registry.register(
        Tool(
            name="estado_caja",
            description="Estado actual de la caja: si esta abierta, saldo esperado y turno vigente.",
            parameters={"type": "object", "properties": {}},
            required_permission="cash_shift.manage",
        )
    )

    registry.register(
        Tool(
            name="inventario",
            description="Listado de inventario, opcionalmente filtrado por categoria.",
            parameters={
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "description": "Nombre de la categoria a filtrar."},
                },
            },
            required_permission="inventory.view",
        )
    )

    registry.register(
        Tool(
            name="stock_producto",
            description="Existencias actuales de un producto puntual por nombre.",
            parameters={
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Nombre del producto, tal como aparece en el catalogo."},
                },
                "required": ["producto"],
            },
            required_permission="inventory.view",
        )
    )

    registry.register(
        WriteTool(
            name="crear_gasto",
            description="Registra un gasto del negocio. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "concepto": {"type": "string"},
                    "monto": {"type": "number", "minimum": 0},
                    "tipo_gasto": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD, por defecto hoy."},
                },
                "required": ["concepto", "monto"],
            },
            required_permission="expenses.create",
            required_feature="expenses",
            draft_type="gasto",
            summarize=lambda values: f"Gasto: {values.get('concepto')} por ${values.get('monto')}",
            fields=lambda _context: {
                "concepto": {"type": "string", "label": "Concepto"},
                "monto": {"type": "number", "label": "Monto"},
                "tipo_gasto": {"type": "string", "label": "Tipo de gasto"},
                "fecha": {"type": "date", "label": "Fecha"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_producto",
            description="Crea un producto en el catalogo. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "precio": {"type": "number", "minimum": 0},
                    "costo": {"type": "number", "minimum": 0},
                    "categoria": {"type": "string"},
                },
                "required": ["nombre", "precio"],
            },
            required_permission="inventory.add",
            draft_type="producto",
            summarize=lambda values: f"Producto: {values.get('nombre')} - ${values.get('precio')}",
            fields=lambda _context: {
                "nombre": {"type": "string", "label": "Nombre"},
                "precio": {"type": "number", "label": "Precio de venta"},
                "costo": {"type": "number", "label": "Costo"},
                "categoria": {"type": "string", "label": "Categoria"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_cliente",
            description="Registra un cliente nuevo. Crea un borrador que el usuario debe confirmar.",
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "telefono": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["nombre"],
            },
            required_permission="clients.manage",
            required_feature="clients",
            draft_type="cliente",
            summarize=lambda values: f"Cliente: {values.get('nombre')}",
            fields=lambda _context: {
                "nombre": {"type": "string", "label": "Nombre"},
                "telefono": {"type": "string", "label": "Telefono"},
                "email": {"type": "string", "label": "Email"},
            },
        )
    )

    return registry
