"""Herramientas de la app del hogar.

Igual que en el POS y el Spa, esto es SOLO metadata: nombre, descripcion y
JSON Schema. La ejecucion viaja por `AppToolClient` hacia
`POST {base_url}/api/ai/tools/invoke` del lado de la app (FastAPI), donde
viven el libro de cuentas, los recibos, las tareas y los almuerzos.

Los `name` son el contrato compartido con el diccionario `HANDLERS` de
`hogar_app/api/ai/tools.py`: cambiar uno aca sin cambiarlo alla rompe la
herramienta en silencio (el modelo la ofrece, la app contesta que no existe).

**Que pasa por borrador y que no, a proposito.** El mecanismo de borradores
existe para que una alucinacion no mueva plata real. Asi que TODO lo que toca
el saldo -- gastos, prestamos, abonos, recibos, precios y almuerzos, que son
deuda con quien los pone -- es `WriteTool` y espera confirmacion. Las tareas y
la lista de mercado NO: agregar "leche" mal escrito cuesta cero y pedir una
tarjeta de confirmacion para cada cosa del mercado convierte una frase en
cuatro toques. El riesgo y la friccion tienen que guardar proporcion.

No hay `required_permission` ni `required_feature` en ninguna: en la casa
viven dos personas y ven lo mismo. Su `GET /api/ai/tools/catalog` lo confirma
devolviendo null en las dos, para que el catalogo remoto no se quede con
defaults inventados.
"""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.registry import ToolRegistry

_RANGO = {
    "desde": {"type": "string", "description": "Fecha inicial YYYY-MM-DD."},
    "hasta": {"type": "string", "description": "Fecha final YYYY-MM-DD."},
}

_FECHA = {"type": "string", "description": "YYYY-MM-DD, por defecto hoy."}


def _pesos(monto: object) -> str:
    """La tarjeta de confirmacion la lee una persona en Colombia. `f"{n:,}"`
    escribe "$200,000", y ahi la coma es el separador DECIMAL: se lee como
    doscientos pesos. Si el modelo mando algo que no es un numero, se muestra
    tal cual en vez de reventar el borrador."""
    try:
        return f"${int(monto):,}".replace(",", ".")
    except (TypeError, ValueError):
        return f"${monto}"


def _resumir_gasto(values: dict) -> str:
    reparto = values.get("para") or values.get("se_reparte_entre")
    quien = f" (solo de {reparto})" if isinstance(reparto, str) else ""
    return f"Gasto: {values.get('concepto')} por {_pesos(values.get('monto'))}{quien}"


def _resumir_precio(values: dict) -> str:
    """Tiene que decir SOBRE QUE periodo aplica: confirmar "almuerzo a
    $13.000" sin saber si es para septiembre o de aca en adelante no es
    confirmar nada."""
    if values.get("mes"):
        periodo = values["mes"]
    elif values.get("anio"):
        periodo = f"todo {values['anio']}"
    elif values.get("hasta"):
        periodo = f"del {values.get('desde')} al {values['hasta']}"
    else:
        periodo = f"desde {values.get('desde', 'hoy')}"

    return f"Almuerzo a {_pesos(values.get('precio_unitario'))} ({periodo})"


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    # --- Consultas ---------------------------------------------------------

    registry.register(
        Tool(
            name="saldos",
            description=(
                "Quien le debe a quien en la casa y cuanto, con nombres. Incluye el "
                "acumulado de almuerzos. Uselo para '¿como vamos?', '¿cuanto le debo?', "
                "'¿quien debe mas?'."
            ),
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="movimientos",
            description=(
                "Los gastos, prestamos y abonos de un rango de fechas, con quien pago "
                "cada uno. Sin fechas, el mes en curso. Uselo para '¿en que se nos fue "
                "la plata?' o '¿cuanto llevamos gastado?'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_RANGO,
                    "tipo": {"type": "string", "enum": ["gasto", "prestamo", "abono"]},
                },
            },
        )
    )

    registry.register(
        Tool(
            name="personas",
            description=(
                "Quienes estan en el libro de cuentas y quienes viven en la casa. Uselo "
                "si necesita saber a quien se puede nombrar en un gasto o una tarea."
            ),
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="recibos_pendientes",
            description=(
                "Lo que esta por pagarse, con cuantos dias faltan y cuales ya se "
                "vencieron. Uselo para '¿que debemos pagar?', '¿ya pagamos el "
                "arriendo?', '¿que se vence esta semana?'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dias": {
                        "type": "integer",
                        "description": "Cuantos dias hacia adelante mirar. Por defecto 30.",
                    }
                },
            },
        )
    )

    registry.register(
        Tool(
            name="tareas_pendientes",
            description="Las tareas de la casa sin completar, de quien son y cuando vencen.",
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="lista_mercado",
            description="Que falta comprar y que ya se marco como comprado.",
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="almuerzos_resumen",
            description=(
                "Cuantos almuerzos hubo en un rango y cuanto valen, con el detalle por "
                "precio vigente. Sin fechas, el mes en curso."
            ),
            parameters={"type": "object", "properties": dict(_RANGO)},
        )
    )

    registry.register(
        Tool(
            name="precio_almuerzo_vigente",
            description=(
                "Cuanto vale un almuerzo en una fecha (por defecto hoy). Devuelve "
                "`hay_precio: false` si esa fecha no la cubre ninguna vigencia."
            ),
            parameters={"type": "object", "properties": {"fecha": dict(_FECHA)}},
        )
    )

    # --- Escrituras que mueven plata: pasan por borrador --------------------

    registry.register(
        WriteTool(
            name="registrar_gasto",
            description=(
                "Registra un gasto. Por defecto lo pago quien escribe y se reparte "
                "entre quienes viven en la casa. Use `para` con UN nombre cuando el "
                "gasto es de una sola persona ('esto fue solo mio', 'la ropa de Ana'). "
                "Crea un borrador que se debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "concepto": {"type": "string"},
                    "monto": {"type": "integer", "minimum": 1},
                    "fecha": dict(_FECHA),
                    "pagado_por": {
                        "type": "string",
                        "description": "Nombre de quien puso la plata. Por defecto, quien escribe.",
                    },
                    "para": {
                        "type": "string",
                        "description": "Nombre de la unica persona a la que le corresponde el gasto.",
                    },
                    "categoria": {"type": "string"},
                },
                "required": ["concepto", "monto"],
            },
            draft_type="gasto",
            summarize=_resumir_gasto,
            fields=lambda _context: {
                "concepto": {"type": "string", "label": "Concepto"},
                "monto": {"type": "number", "label": "Monto"},
                "fecha": {"type": "date", "label": "Fecha"},
                "pagado_por": {"type": "string", "label": "Lo pago"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="registrar_prestamo",
            description=(
                "Registra plata que una persona le presta a otra. Distinto de un gasto: "
                "no se reparte, se debe completo. Crea un borrador que se debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "monto": {"type": "integer", "minimum": 1},
                    "a_quien": {"type": "string", "description": "Nombre de quien recibe."},
                    "de_quien": {
                        "type": "string",
                        "description": "Nombre de quien presta. Por defecto, quien escribe.",
                    },
                    "concepto": {"type": "string"},
                    "fecha": dict(_FECHA),
                },
                "required": ["monto", "a_quien"],
            },
            draft_type="prestamo",
            summarize=lambda values: (
                f"Prestamo de {_pesos(values.get('monto'))} a {values.get('a_quien')}"
            ),
            fields=lambda _context: {
                "monto": {"type": "number", "label": "Monto"},
                "a_quien": {"type": "string", "label": "A quien"},
                "fecha": {"type": "date", "label": "Fecha"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="registrar_abono",
            description=(
                "Registra un pago que salda (total o parcialmente) una deuda entre dos "
                "personas. Uselo para 'le pague a Ana 50 mil', 'le di 200 mil a mama'. "
                "Crea un borrador que se debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "monto": {"type": "integer", "minimum": 1},
                    "a_quien": {"type": "string", "description": "Nombre de quien recibe el abono."},
                    "de_quien": {
                        "type": "string",
                        "description": "Nombre de quien abona. Por defecto, quien escribe.",
                    },
                    "fecha": dict(_FECHA),
                },
                "required": ["monto", "a_quien"],
            },
            draft_type="abono",
            summarize=lambda values: (
                f"Abono de {_pesos(values.get('monto'))} a {values.get('a_quien')}"
            ),
            fields=lambda _context: {
                "monto": {"type": "number", "label": "Monto"},
                "a_quien": {"type": "string", "label": "A quien"},
                "fecha": {"type": "date", "label": "Fecha"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="pagar_recibo",
            description=(
                "Marca pagado un recibo pendiente y lo lleva al libro de cuentas. El "
                "monto es el REAL, el que llego, no el estimado. Crea un borrador que se "
                "debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del recibo, p.ej. 'arriendo'."},
                    "monto_real": {"type": "integer", "minimum": 1},
                    "pagado_por": {"type": "string"},
                    "fecha": dict(_FECHA),
                },
                "required": ["nombre", "monto_real"],
            },
            draft_type="recibo",
            summarize=lambda values: (
                f"Pagar {values.get('nombre')} por {_pesos(values.get('monto_real'))}"
            ),
            fields=lambda _context: {
                "nombre": {"type": "string", "label": "Recibo"},
                "monto_real": {"type": "number", "label": "Monto real"},
                "fecha": {"type": "date", "label": "Fecha"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="crear_cuenta_fija",
            description=(
                "Crea algo que vuelve cada mes con fecha de vencimiento (arriendo, luz, "
                "internet). A partir de ahi genera un recibo cada mes y entra en los "
                "recordatorios. Crea un borrador que se debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "dia_vencimiento": {"type": "integer", "minimum": 1, "maximum": 31},
                    "monto_estimado": {"type": "integer", "minimum": 1},
                    "avisar_dias_antes": {"type": "integer", "minimum": 0, "maximum": 30},
                    "categoria": {"type": "string"},
                },
                "required": ["nombre", "dia_vencimiento"],
            },
            draft_type="cuenta_fija",
            summarize=lambda values: (
                f"{values.get('nombre')}: vence el {values.get('dia_vencimiento')} de cada mes"
            ),
            fields=lambda _context: {
                "nombre": {"type": "string", "label": "Nombre"},
                "dia_vencimiento": {"type": "number", "label": "Dia de vencimiento"},
                "monto_estimado": {"type": "number", "label": "Monto estimado"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="registrar_almuerzo",
            description=(
                "Registra los almuerzos de UN dia. Si no se dice la cantidad, usa la de "
                "siempre. Crea un borrador que se debe confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fecha": dict(_FECHA),
                    "cantidad": {"type": "integer", "minimum": 0, "maximum": 10},
                    "nota": {"type": "string"},
                },
            },
            draft_type="almuerzo",
            summarize=lambda values: (
                f"Almuerzos del {values.get('fecha', 'hoy')}: "
                f"{values.get('cantidad', 'los de siempre')}"
            ),
            fields=lambda _context: {
                "fecha": {"type": "date", "label": "Fecha"},
                "cantidad": {"type": "number", "label": "Cuantos almuerzos"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="marcar_almuerzos",
            description=(
                "Marca de una vez todos los dias de un rango que caigan en ciertos dias "
                "de la semana (por defecto, los habiles). Es la forma de cargar un mes "
                "completo. Con cantidad 0, los borra. Crea un borrador que se debe "
                "confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_RANGO,
                    "cantidad": {"type": "integer", "minimum": 0, "maximum": 10},
                    "dias_semana": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1, "maximum": 7},
                        "description": "1 = lunes ... 7 = domingo. Por defecto, de lunes a viernes.",
                    },
                },
            },
            draft_type="almuerzos_rango",
            summarize=lambda values: (
                f"Marcar {values.get('cantidad', 2)} almuerzos por dia "
                f"del {values.get('desde', '?')} al {values.get('hasta', '?')}"
            ),
            fields=lambda _context: {
                "desde": {"type": "date", "label": "Desde"},
                "hasta": {"type": "date", "label": "Hasta"},
                "cantidad": {"type": "number", "label": "Almuerzos por dia"},
            },
        )
    )

    registry.register(
        WriteTool(
            name="definir_precio_almuerzo",
            description=(
                "Define cuanto vale un almuerzo durante un periodo. Crea un borrador que "
                "se debe confirmar.\n"
                "Como elegir el periodo -- importa, porque decide hasta cuando rige:\n"
                "- 'desde octubre vale 13 mil', 'subio a 13 mil': use `desde` con el "
                "primer dia (2026-10-01) y NO mande `hasta`. Queda vigente hasta que "
                "haya otro precio; es el caso normal cuando el precio sube.\n"
                "- 'en octubre valio 13 mil', 'solo ese mes': use `mes` ('2026-10'). "
                "Eso lo acota a ese mes y despues vuelve a regir el precio anterior.\n"
                "- 'todo el año vale 12 mil': use `anio`."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "precio_unitario": {"type": "integer", "minimum": 1},
                    "mes": {"type": "string", "description": "YYYY-MM, por ejemplo 2026-09."},
                    "anio": {"type": "integer", "minimum": 2000, "maximum": 2100},
                    "desde": {"type": "string", "description": "YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "YYYY-MM-DD, opcional."},
                },
                "required": ["precio_unitario"],
            },
            draft_type="precio",
            summarize=_resumir_precio,
            fields=lambda _context: {
                "precio_unitario": {"type": "number", "label": "Precio de un almuerzo"},
                "mes": {"type": "string", "label": "Mes (YYYY-MM)"},
                "desde": {"type": "date", "label": "Desde"},
            },
        )
    )

    # --- Escrituras de bajo riesgo: directas -------------------------------
    #
    # Ver el docstring del modulo: una tarjeta de confirmacion por cada cosa
    # del mercado convierte una frase en cuatro toques, y el dano de un
    # "leche" de mas es cero.

    registry.register(
        Tool(
            name="crear_tarea",
            description=(
                "Agrega una tarea de la casa. Puede repetirse (diaria, semanal, "
                "quincenal, mensual) y turnarse entre quienes viven ahi. Se guarda de "
                "una, sin confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "para": {"type": "string", "description": "Nombre de a quien le toca."},
                    "vence": dict(_FECHA),
                    "repeticion": {
                        "type": "string",
                        "enum": ["ninguna", "diaria", "semanal", "quincenal", "mensual"],
                    },
                    "rotar": {
                        "type": "boolean",
                        "description": "Si se repite, alternar de persona cada vez.",
                    },
                },
                "required": ["titulo"],
            },
        )
    )

    registry.register(
        Tool(
            name="completar_tarea",
            description=(
                "Marca hecha una tarea pendiente, buscandola por su titulo. Si se "
                "repite, deja creada la siguiente. Se guarda de una, sin confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {"titulo": {"type": "string"}},
                "required": ["titulo"],
            },
        )
    )

    registry.register(
        Tool(
            name="agregar_al_mercado",
            description=(
                "Agrega una o varias cosas a la lista de mercado de una sola vez "
                "('anota leche, pan y huevos'). Se guarda de una, sin confirmar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "articulos": {"type": "array", "items": {"type": "string"}},
                    "cantidad": {
                        "type": "string",
                        "description": "Solo si es UN articulo: '2 kg', 'un frasco'.",
                    },
                },
                "required": ["articulos"],
            },
        )
    )

    registry.register(
        Tool(
            name="marcar_comprado",
            description="Marca comprado un articulo de la lista de mercado, por su nombre.",
            parameters={
                "type": "object",
                "properties": {"nombre": {"type": "string"}},
                "required": ["nombre"],
            },
        )
    )

    return registry
