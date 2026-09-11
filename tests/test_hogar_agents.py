"""El bundle de la app del hogar.

Lo que se defiende aca es el contrato con `hogar-app`: los nombres de las
herramientas son un string compartido entre dos repos (el diccionario
`HANDLERS` de `hogar_app/api/ai/tools.py`), y un typo de este lado no rompe
nada visible -- el modelo ofrece la herramienta, la app contesta que no
existe y queda un asistente que "no sabe" hacer lo que promete.
"""
from __future__ import annotations

import pytest

from nexolu_ia_core.apps.hogar.agents import build_agent_registry
from nexolu_ia_core.apps.hogar.tools import build_tool_registry
from nexolu_ia_core.apps.registry import get_app_bundle

# Los veinte nombres tal como los despacha la app. Esta lista es el contrato:
# cambiarla sin cambiar el otro repo (o al reves) es lo que este test atrapa.
CONTRATO = {
    "saldos",
    "movimientos",
    "personas",
    "recibos_pendientes",
    "tareas_pendientes",
    "lista_mercado",
    "almuerzos_resumen",
    "precio_almuerzo_vigente",
    "registrar_gasto",
    "registrar_prestamo",
    "registrar_abono",
    "pagar_recibo",
    "crear_cuenta_fija",
    "crear_tarea",
    "completar_tarea",
    "agregar_al_mercado",
    "marcar_comprado",
    "registrar_almuerzo",
    "marcar_almuerzos",
    "definir_precio_almuerzo",
}

# Todo lo que toca el saldo. Ver el docstring de apps/hogar/tools.py: el
# borrador existe para que una alucinacion no mueva plata real.
MUEVEN_PLATA = {
    "registrar_gasto",
    "registrar_prestamo",
    "registrar_abono",
    "pagar_recibo",
    "crear_cuenta_fija",
    "registrar_almuerzo",
    "marcar_almuerzos",
    "definir_precio_almuerzo",
}


def test_el_bundle_se_resuelve_por_app_id() -> None:
    bundle = get_app_bundle("hogar")

    assert bundle.app_id == "hogar"
    assert bundle.display_name == "Hogar"


def test_los_nombres_son_exactamente_los_que_la_app_despacha() -> None:
    assert set(build_tool_registry().all()) == CONTRATO


def test_todas_las_herramientas_del_agente_existen() -> None:
    disponibles = set(build_tool_registry().all())

    for agente in build_agent_registry().all().values():
        faltantes = set(agente.tool_names) - disponibles
        assert not faltantes, f"{agente.name} declara herramientas que no existen: {faltantes}"


def test_el_agente_ofrece_todo_el_catalogo() -> None:
    """Una herramienta declarada que ningun agente ofrece es codigo muerto:
    el modelo nunca la ve."""
    agente = build_agent_registry().get("casa")

    assert set(agente.tool_names) == CONTRATO


def test_todo_lo_que_mueve_plata_pasa_por_un_borrador() -> None:
    registry = build_tool_registry().all()

    for nombre in MUEVEN_PLATA:
        assert registry[nombre].is_write(), f"{nombre} mueve plata sin confirmacion humana"


def test_las_tareas_y_el_mercado_no_piden_confirmacion() -> None:
    """Una tarjeta de confirmacion por cada cosa del mercado convierte una
    frase en cuatro toques, y el dano de un 'leche' de mas es cero."""
    registry = build_tool_registry().all()

    for nombre in ("crear_tarea", "completar_tarea", "agregar_al_mercado", "marcar_comprado"):
        assert not registry[nombre].is_write()


def test_las_consultas_no_generan_borradores() -> None:
    registry = build_tool_registry().all()

    for nombre in ("saldos", "movimientos", "recibos_pendientes", "lista_mercado"):
        assert not registry[nombre].is_write()


def test_ninguna_herramienta_pide_permisos() -> None:
    """La app no tiene sistema de permisos: en la casa viven dos personas y
    ven lo mismo."""
    for tool in build_tool_registry().all().values():
        assert tool.required_permission is None
        assert tool.required_feature is None


@pytest.mark.parametrize(
    ("valores", "esperado"),
    [
        ({"precio_unitario": 13000, "mes": "2026-09"}, "2026-09"),
        ({"precio_unitario": 13000, "anio": 2026}, "todo 2026"),
        ({"precio_unitario": 13000, "desde": "2026-10-01"}, "desde 2026-10-01"),
        (
            {"precio_unitario": 13000, "desde": "2026-10-01", "hasta": "2026-10-31"},
            "del 2026-10-01 al 2026-10-31",
        ),
    ],
)
def test_la_tarjeta_de_precio_dice_sobre_que_periodo_aplica(valores: dict, esperado: str) -> None:
    """Confirmar "almuerzo a $13.000" sin saber si es para septiembre o de
    aca en adelante no es confirmar nada."""
    resumen = build_tool_registry().all()["definir_precio_almuerzo"].summarize(valores)

    assert esperado in resumen
    assert "$13.000" in resumen


def test_la_plata_de_las_tarjetas_se_escribe_a_la_colombiana() -> None:
    """`f"{n:,}"` da "$200,000", y en Colombia esa coma es el separador
    DECIMAL: se lee como doscientos pesos."""
    resumen = build_tool_registry().all()["registrar_abono"].summarize(
        {"monto": 200000, "a_quien": "Mama"}
    )

    assert "$200.000" in resumen
    assert "Mama" in resumen


def test_una_tarjeta_con_un_monto_raro_no_revienta() -> None:
    """Lo que llega es lo que escribio un modelo: puede mandar texto donde va
    un numero, y el borrador tiene que poder mostrarse igual."""
    resumen = build_tool_registry().all()["registrar_abono"].summarize(
        {"monto": "doscientos mil", "a_quien": "Ana"}
    )

    assert "doscientos mil" in resumen
