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

    # ── Portadas del chat del legacy (2026-09-02) ───────────────────────────
    # Ninguna se usaba alli -- ese chat murio con 19 conversaciones -- pero el
    # catalogo se construyo respondiendo preguntas reales de dueños de local, y
    # lo que costaba era descubrir cuales hacian falta, no escribirlas. Las
    # descripciones traen los ejemplos textuales de esas preguntas a proposito:
    # es lo unico que el modelo tiene para decidir cual usar.

    registry.register(
        Tool(
            name="ventas_historico",
            description=(
                "Total vendido de TODA la historia del negocio, mes a mes, con la fecha de la "
                "primera venta y el promedio mensual. Usala para \"cuanto he vendido desde que "
                "tengo el programa\", \"cual ha sido mi mejor mes\" o cualquier pregunta sobre "
                "periodos largos o sin fecha de inicio: averigua sola desde cuando hay datos, no "
                "se la preguntes al usuario. Para periodos cortos y concretos usa ventas_resumen."
            ),
            parameters={"type": "object", "properties": {}},
            required_permission="reports.sales",
        )
    )

    registry.register(
        Tool(
            name="ventas_por_vendedor",
            description=(
                "Ventas agrupadas por el vendedor que las cerro, con total, numero de ventas y "
                "ticket promedio. Usala para \"quien vendio mas\", \"ventas por empleado\" o "
                "\"que hizo Juan esta semana\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "nombre_vendedor": {"type": "string", "description": "Opcional. Filtra por nombre del vendedor."},
                },
            },
            required_permission="reports.sales_by_seller",
        )
    )

    registry.register(
        Tool(
            name="metodos_de_pago",
            description=(
                "Como entro la plata en un periodo: total por cada medio de pago. Incluye ventas, "
                "abonos a fiados, abonos a apartados y pagos de servicios. Usala para \"cuanto "
                "entro en efectivo\", \"cuanto me pagaron por transferencia\" o \"que porcentaje "
                "es efectivo\". Cubre maximo 92 dias."
            ),
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
            name="productos_top",
            description=(
                "Productos mas o menos vendidos de un periodo, con unidades e ingresos. Usala para "
                "\"que es lo que mas se vende\", \"productos estrella\" o \"que se vende poco\". "
                "OJO: menos_vendidos lista lo que SI se vendio poco; lo que no se vendio nada no "
                "aparece, para eso usa inventario."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "orden": {"type": "string", "enum": ["mas_vendidos", "menos_vendidos"]},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="reports.sales",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="cuentas_abiertas",
            description=(
                "Mesas o cuentas abiertas en este momento, con su consumo acumulado y hace cuanto "
                "estan abiertas. Usala para \"que mesas tengo abiertas\", \"cuantas cuentas hay "
                "sin cerrar\" o \"cuanto hay en las mesas\"."
            ),
            parameters={"type": "object", "properties": {}},
            required_feature="open_tabs",
        )
    )

    registry.register(
        Tool(
            name="historial_cuenta",
            description=(
                "Que se vendio en una cuenta y el rastro de quien la abrio, quien agrego o saco "
                "items y quien la cerro. Usala para \"que se le vendio a [cliente]\", \"quien saco "
                "[producto] de la cuenta de [cliente]\" o \"que paso con la venta numero X\". "
                "Necesita al menos cliente o venta_id."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cliente": {"type": "string", "description": "Nombre o parte del nombre del cliente."},
                    "venta_id": {"type": "integer", "minimum": 1},
                    "producto": {"type": "string", "description": "Opcional. Filtra el rastro a un producto puntual."},
                    "dias": {"type": "integer", "minimum": 1, "maximum": 365, "description": "Ventana hacia atras buscando por cliente. Por defecto 90."},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 20},
                },
            },
            required_permission="reports.sales",
        )
    )

    registry.register(
        Tool(
            name="clientes_frecuentes",
            description=(
                "Clientes ordenados por cuanto han gastado, con visitas y ultima compra. Usala "
                "para \"quien es mi mejor cliente\" o \"cuanto ha gastado un cliente\". Para "
                "clientes perdidos (\"quien compraba seguido y dejo de venir\") usa "
                "orden=hace_mas_que_no_vienen, que excluye a quien solo compro una vez."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_cliente": {"type": "string"},
                    "orden": {"type": "string", "enum": ["mas_gastan", "mas_visitan", "hace_mas_que_no_vienen"]},
                    "minimo_visitas": {"type": "integer", "minimum": 1, "description": "Solo con orden=hace_mas_que_no_vienen. Por defecto 2."},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="clients.manage",
        )
    )

    registry.register(
        Tool(
            name="fiados_pendientes",
            description=(
                "Fiados con saldo pendiente, agrupados por cliente, con el total adeudado y desde "
                "cuando. Usala para \"cuanto me deben\", \"quien me debe\" o \"que fiados estan "
                "vencidos\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_cliente": {"type": "string"},
                    "incluir_pagados": {"type": "boolean", "description": "Por defecto solo los pendientes."},
                },
            },
            required_permission="receivables.manage",
            required_feature="receivables",
        )
    )

    registry.register(
        Tool(
            name="gastos_resumen",
            description=(
                "Gastos de un periodo con el total y el desglose por tipo. Usala para \"cuanto "
                "gaste este mes\", \"en que se me va la plata\" o \"gastos de la semana\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                },
            },
            required_permission="expenses.manage",
            required_feature="expenses",
        )
    )

    registry.register(
        Tool(
            name="inventario_reposicion",
            description=(
                "Productos ordenados por urgencia real de reposicion: cruza el stock con la "
                "velocidad de venta reciente y estima cuantos dias de cobertura quedan. Usala para "
                "\"que debo comprar\", \"que se me va a acabar\" o \"productos por agotarse\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dias_analisis": {"type": "integer", "minimum": 7, "maximum": 90, "description": "Ventana para calcular la velocidad de venta. Por defecto 30."},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="inventory.view",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="ingredientes_stock",
            description=(
                "Existencias de ingredientes con unidad, minimo y costo, ordenados por urgencia de "
                "reposicion. Usala para \"que insumos se me estan acabando\", \"cuanto queda de "
                "un insumo\" o \"cuanto vale mi inventario de ingredientes\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "solo_bajo_minimo": {"type": "boolean"},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="inventory.view",
            required_feature="ingredients",
        )
    )

    registry.register(
        Tool(
            name="margenes_producto",
            description=(
                "Margen de ganancia por producto en un periodo: unidades vendidas, precio, costo y "
                "utilidad. Usala para \"cuanto gano por producto\", \"que producto deja mas "
                "ganancia\" o \"cual es mi margen\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "orden": {"type": "string", "enum": ["mas_utilidad", "menos_utilidad", "mejor_margen"]},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="reports.inventory",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="calcular_precio",
            description=(
                "Calcula el precio de venta para un margen objetivo, o el margen que deja un "
                "precio. Usala para \"a como vendo esto para ganar 30%\", \"que margen tengo si "
                "vendo a 15 mil\" o \"a cuanto deberia vender esto\". Pide exactamente uno de "
                "margen_deseado o precio_venta, y exactamente uno de producto o costo."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Para tomar su costo actual. Alternativa a costo."},
                    "costo": {"type": "number", "exclusiveMinimum": 0, "description": "Costo directo. Alternativa a producto."},
                    "margen_deseado": {"type": "number", "exclusiveMinimum": 0, "maximum": 99, "description": "Margen objetivo en porcentaje DEL PRECIO DE VENTA, no del costo."},
                    "precio_venta": {"type": "number", "exclusiveMinimum": 0},
                },
            },
            required_permission="reports.inventory",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="receta_producto",
            description=(
                "Ingredientes de un producto con la cantidad de cada uno, el costo de producirlo y "
                "el margen que deja. Usala para \"que lleva la hamburguesa\", \"cuanto me cuesta "
                "prepararla\" o \"cuanto gano con ese plato\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_producto": {"type": "string"},
                },
                "required": ["nombre_producto"],
            },
            required_permission="reports.inventory",
            required_feature="ingredients",
        )
    )

    registry.register(
        Tool(
            name="variacion_costo_producto",
            description=(
                "Como ha cambiado el costo de compra de un producto: el precio pagado en cada "
                "compra y a que proveedor, con minimo, maximo y comparativa entre proveedores. "
                "Usala para \"me subieron el precio de algo\", \"a que proveedor me sale mas "
                "barato\" o \"cuanto me costaba antes\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_producto": {"type": "string"},
                    "limite_compras": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["nombre_producto"],
            },
            required_permission="reports.inventory",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="historial_stock",
            description=(
                "Quien movio el stock de un producto o ingrediente: cada entrada, salida o ajuste "
                "manual con fecha, cantidad y quien lo hizo. Usala para \"quien modifico el stock "
                "de X\" o \"quien toco el inventario de X\". NO incluye las salidas por venta."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del producto o ingrediente, tal como lo dijo el usuario."},
                    "dias": {"type": "integer", "minimum": 1, "maximum": 365, "description": "Por defecto 14."},
                },
                "required": ["nombre"],
            },
            required_permission="inventory.view",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="proveedores",
            description=(
                "Proveedores registrados con sus datos de contacto, cuantas compras se les ha "
                "hecho, el total comprado y la ultima compra. Usala para \"que proveedores tengo\", "
                "\"hace cuanto no le compro a alguien\" o \"datos de contacto de un proveedor\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_proveedor": {"type": "string"},
                },
            },
            required_permission="purchases.manage",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="compras_resumen",
            description=(
                "Compras a proveedores en un periodo: total comprado, numero de compras y desglose "
                "por proveedor. Usala para \"cuanto compre este mes\" o \"a que proveedor le "
                "compro mas\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                },
            },
            required_permission="purchases.manage",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="compras_detalle",
            description=(
                "Las compras una por una, con proveedor, fecha, factura y total. Usala para \"cual "
                "fue la compra mas costosa\", \"que compre el mes pasado\" o \"muestrame las "
                "ultimas compras\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "orden": {"type": "string", "enum": ["mas_costosa", "mas_reciente", "menos_costosa"]},
                    "nombre_proveedor": {"type": "string"},
                    "limite": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            required_permission="purchases.manage",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="cuentas_por_pagar",
            description=(
                "Compras pendientes de pago agrupadas por proveedor, con el saldo adeudado y desde "
                "cuando. Usala para \"cuanto le debo a mis proveedores\" o \"a quien le debo mas\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre_proveedor": {"type": "string"},
                },
            },
            required_permission="purchases.manage",
            required_feature="inventory",
        )
    )

    registry.register(
        Tool(
            name="apartados",
            description=(
                "Apartados con el cliente, el total, lo abonado y el saldo pendiente. Usala para "
                "\"que productos tengo apartados\", \"cuanto me deben de apartados\" o \"quien "
                "tiene productos separados\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "estado": {"type": "string", "description": "Opcional. Filtra por estado del apartado."},
                },
            },
            required_permission="layaways.manage",
            required_feature="layaway",
        )
    )

    registry.register(
        Tool(
            name="citas_agendadas",
            description=(
                "Citas agendadas con fecha, hora, cliente, servicio y estado. Usala para \"que "
                "citas hay hoy\", \"que tengo agendado esta semana\" o \"quien viene manana\". "
                "Sin fechas mira los proximos 30 dias, no hacia atras."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "estado": {"type": "string"},
                },
            },
            required_permission="appointments.manage",
            required_feature="scheduling",
        )
    )

    registry.register(
        Tool(
            name="servicios_estado",
            description=(
                "Ordenes de servicio con cliente, estado, total, abonado y saldo pendiente. Usala "
                "para \"que servicios tengo\", \"cuales estan pendientes\" o \"cuanto me deben "
                "por servicios\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
                    "nombre_cliente": {"type": "string"},
                    "solo_pendientes": {"type": "boolean"},
                },
            },
            required_permission="appointments.manage",
            required_feature="services",
        )
    )

    registry.register(
        Tool(
            name="recordatorios_pendientes",
            description=(
                "Recordatorios pendientes del planificador, ordenados por fecha. Usala para \"que "
                "tengo pendiente\" o \"que se me viene esta semana\"."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "minimum": 1, "maximum": 90, "description": "Techo de fecha. Los vencidos entran siempre."},
                },
            },
            required_permission="reminders.manage",
            required_feature="reminders",
        )
    )

    registry.register(
        WriteTool(
            name="crear_recordatorio",
            description=(
                "Crea un recordatorio. Genera un borrador que el usuario debe confirmar. Usala "
                "cuando pidan \"recuerdame manana hacer inventario\" o \"recuerdame cada semana "
                "revisar la nevera\". Convierte las fechas relativas (\"manana\", \"el viernes\") "
                "a YYYY-MM-DD usando la fecha de hoy que tienes en el contexto."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD, ya convertida."},
                    "recurrencia": {"type": "string", "enum": ["none", "daily", "weekly", "monthly", "yearly"]},
                    "repetir_hasta": {"type": "string", "description": "Opcional, solo si es recurrente. YYYY-MM-DD."},
                    "nota": {"type": "string"},
                },
                "required": ["titulo", "fecha"],
            },
            required_permission="reminders.manage",
            required_feature="reminders",
            draft_type="recordatorio",
            summarize=lambda values: f"Recordatorio: {values.get('titulo')} para el {values.get('fecha')}",
            fields=lambda _context: {
                "titulo": {"type": "string", "label": "Recordar"},
                "fecha": {"type": "date", "label": "Fecha"},
                "nota": {"type": "string", "label": "Nota"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_entrada_inventario",
            description=(
                "Registra una entrada de stock de un producto. Genera un borrador que el usuario "
                "debe confirmar. Usala cuando digan que surtieron, repusieron o llegaron unidades: "
                "\"surti 15 empanadas\", \"llegaron 20 gaseosas\". "
                "IMPORTANTE: SUMA al stock actual, no lo reemplaza. Si quieren dejar el stock en un "
                "numero exacto (\"el stock quedo en 15\", \"corrige el inventario a 15\") NO la "
                "uses: dile que ese ajuste lo haga en Inventario, en la ficha del producto. Ante la "
                "duda de si quiso sumar o corregir, preguntale antes. "
                "Si menciona lo que pago, usa valor_total O valor_unitario segun como lo dijo, "
                "nunca los dos; si no menciona plata, no preguntes por eso."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Nombre tal como lo dijo el usuario. No lo corrijas ni lo completes con un nombre de un turno anterior."},
                    "cantidad": {"type": "number", "exclusiveMinimum": 0, "description": "Cuantas unidades ENTRAN, no el total que debe quedar."},
                    "nota": {"type": "string"},
                    "valor_total": {"type": "number", "exclusiveMinimum": 0, "description": "Lo que se pago en TOTAL. No la uses junto con valor_unitario."},
                    "valor_unitario": {"type": "number", "exclusiveMinimum": 0, "description": "Lo que costo CADA unidad. No la uses junto con valor_total."},
                },
                "required": ["producto", "cantidad"],
            },
            required_permission="inventory.add",
            required_feature="inventory",
            draft_type="entrada_inventario",
            summarize=lambda values: f"Entrada: {values.get('cantidad')} de {values.get('producto')}",
            fields=lambda _context: {
                "producto": {"type": "string", "label": "Producto"},
                "cantidad": {"type": "number", "label": "Cantidad que entra"},
                "valor_total": {"type": "number", "label": "Valor total pagado"},
                "nota": {"type": "string", "label": "Nota"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_entrada_ingrediente",
            description=(
                "Registra una entrada de un ingrediente o insumo. Genera un borrador que el "
                "usuario debe confirmar. Usala para materia prima: \"llegaron 5 kilos de queso\", "
                "\"compre 3 litros de aceite\". Para productos terminados que se venden usa "
                "crear_entrada_inventario. "
                "SUMA al stock actual, no lo reemplaza. No conviertas unidades: pasa la cantidad "
                "como la dijo el usuario, la respuesta trae la unidad configurada para que la "
                "verifique."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ingrediente": {"type": "string"},
                    "cantidad": {"type": "number", "exclusiveMinimum": 0},
                    "nota": {"type": "string"},
                    "valor_total": {"type": "number", "exclusiveMinimum": 0, "description": "No la uses junto con valor_unitario."},
                    "valor_unitario": {"type": "number", "exclusiveMinimum": 0, "description": "No la uses junto con valor_total."},
                },
                "required": ["ingrediente", "cantidad"],
            },
            required_permission="inventory.add",
            required_feature="ingredients",
            draft_type="entrada_ingrediente",
            summarize=lambda values: f"Entrada de insumo: {values.get('cantidad')} de {values.get('ingrediente')}",
            fields=lambda _context: {
                "ingrediente": {"type": "string", "label": "Ingrediente"},
                "cantidad": {"type": "number", "label": "Cantidad que entra"},
                "valor_total": {"type": "number", "label": "Valor total pagado"},
                "nota": {"type": "string", "label": "Nota"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_compra",
            description=(
                "Registra una compra a un proveedor. Genera un borrador que el usuario debe "
                "confirmar. Usala cuando digan que le compraron algo a alguien: \"le compre 20 "
                "gaseosas a Postobon por 60 mil\". Suma al stock y actualiza el costo promedio, "
                "igual que la compra manual. "
                "Solo admite UN articulo por compra: si mencionan varios en la misma frase, pideles "
                "que los registren uno a la vez. El proveedor es opcional: si no lo mencionan, NO "
                "se lo preguntes, registrala sin proveedor."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "articulo": {"type": "string", "description": "Producto o insumo comprado, tal como lo dijo el usuario."},
                    "cantidad": {"type": "number", "exclusiveMinimum": 0},
                    "valor_total": {"type": "number", "exclusiveMinimum": 0, "description": "Lo que se pago en total por esa cantidad, no el precio unitario."},
                    "proveedor": {"type": "string", "description": "Opcional."},
                    "nota": {"type": "string"},
                },
                "required": ["articulo", "cantidad", "valor_total"],
            },
            required_permission="purchases.manage",
            draft_type="compra",
            summarize=lambda values: f"Compra: {values.get('cantidad')} de {values.get('articulo')} por ${values.get('valor_total')}",
            fields=lambda _context: {
                "articulo": {"type": "string", "label": "Articulo"},
                "cantidad": {"type": "number", "label": "Cantidad"},
                "valor_total": {"type": "number", "label": "Valor total"},
                "proveedor": {"type": "string", "label": "Proveedor"},
                "nota": {"type": "string", "label": "Nota"},
            },
        )
    )

    return registry
