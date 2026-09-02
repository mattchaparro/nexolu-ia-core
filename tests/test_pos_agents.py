from __future__ import annotations

from nexolu_ia_core.apps.pos.agents import build_agent_registry
from nexolu_ia_core.apps.pos.tools import build_tool_registry


def test_el_asistente_tiene_todas_las_herramientas_del_pos() -> None:
    """
    El caso real que motivo este agente: preguntarle a "cajero" cuanto se
    vendio en agosto respondia "no tengo esa herramienta", porque
    ventas_resumen vivia solo en "analista". El usuario tenia que adivinar
    cual de los cuatro servia para su pregunta.

    Hoy la lista se deriva del registro de herramientas, asi que el olvido es
    imposible por construccion. El test se queda igual: si alguien vuelve a
    enumerarlas a mano -- por ejemplo para excluir una -- esto lo detecta.
    """
    agentes = build_agent_registry()
    # all() devuelve un dict nombre -> Tool.
    herramientas = set(build_tool_registry().all().keys())

    asistente = agentes.get("asistente")

    assert set(asistente.tool_names) == herramientas


def test_los_agentes_especializados_siguen_existiendo() -> None:
    """
    Se conservan por compatibilidad: un cliente viejo que siga mandando
    "cajero" no debe romperse solo porque la interfaz ya no los ofrezca.
    """
    agentes = build_agent_registry()

    for nombre in ("cajero", "analista", "inventario", "restaurante"):
        assert agentes.get(nombre) is not None
