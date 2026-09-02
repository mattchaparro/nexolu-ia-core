"""El bundle del Spa: que ofrece el agente que atiende por WhatsApp.

Quien habla con este agente es una CLIENTA del negocio, no una empleada. Lo
que se defiende aca es que el catalogo que ve el modelo no le ofrezca cosas
que no puede hacer -- ni cosas que no DEBE hacer.
"""
from __future__ import annotations

from nexolu_ia_core.apps.spa.agents import build_agent_registry
from nexolu_ia_core.apps.spa.tools import build_tool_registry


def test_no_existe_una_herramienta_que_enumere_clientes() -> None:
    """La base de clientas del negocio no sale por un chat.

    Es el miedo explicito del dueno: "son mis clientes y podria robarse los
    datos para atenderlos fuera de mi local". El Spa responde 404 a esa
    herramienta; declararla aca solo produciria intentos fallidos y le daria
    al modelo la idea de que existe.
    """
    nombres = set(build_tool_registry().all())

    assert "clientes" not in nombres


def test_todas_las_herramientas_del_agente_existen() -> None:
    """Un `tool_name` que no esta en el registry es una herramienta fantasma.

    El modelo nunca la ve, asi que el sintoma no es un error sino un agente
    que "no sabe" hacer algo que su definicion prometia.
    """
    registry = build_tool_registry()
    disponibles = set(registry.all())

    for agent in build_agent_registry().all().values():
        faltantes = set(agent.tool_names) - disponibles
        assert not faltantes, f"{agent.name} declara herramientas que no existen: {faltantes}"


def test_ninguna_herramienta_es_de_escritura_diferida() -> None:
    """En WhatsApp no hay tarjeta que confirmar.

    Una `WriteTool` crea un borrador y le dice al modelo "la tarjeta ya se le
    mostro al usuario, invitalo a confirmar ahi". Por WhatsApp la clienta
    diria "si" y el modelo generaria otro borrador, en bucle. Aca la
    confirmacion ocurre en palabras, y las instrucciones del agente la exigen.
    """
    assert not any(t.is_write() for t in build_tool_registry().all().values())


def test_el_agente_tiene_con_que_agendar_de_punta_a_punta() -> None:
    agente = build_agent_registry().get("recepcionista")

    # Sin catalogo no puede decir precios; sin disponibilidad inventaria horas.
    for necesaria in ("servicios", "disponibilidad", "crear_cita", "mis_citas"):
        assert necesaria in agente.tool_names
