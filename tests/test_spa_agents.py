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


def test_el_agente_puede_pasar_la_conversacion_a_una_persona() -> None:
    """Sin esto, pedirle al bot "quiero hablar con alguien" no hacia NADA:
    el relevo solo existia si la clienta tocaba el boton de un flujo."""
    agente = build_agent_registry().get("recepcionista")

    assert "hablar_con_persona" in agente.tool_names
    assert "hablar_con_persona" in build_tool_registry().all()


def test_el_agente_puede_mover_una_cita_sin_cancelarla_primero() -> None:
    """Cancelar y volver a crear deja a la clienta sin nada si la hora nueva
    resulto ocupada entre una llamada y la otra."""
    assert "reagendar_cita" in build_agent_registry().get("recepcionista").tool_names


def test_el_prompt_prohibe_hablar_como_mesa_de_ayuda() -> None:
    """Quien atiende es el salon, no una empresa de software: decirle a una
    clienta que la pasan a "soporte tecnico" rompe la ilusion de estar
    hablando con la recepcion."""
    instrucciones = build_agent_registry().get("recepcionista").instructions

    assert "equipo de soporte" in instrucciones  # aparece solo para prohibirlo
    assert "NUNCA" in instrucciones.split("equipo de soporte")[0][-120:]
    assert "administrador" in instrucciones


def test_el_prompt_dice_como_se_ve_un_mensaje_de_whatsapp() -> None:
    """Negrilla para lo que hay que retener y emojis con medida: un parrafo
    plano hay que leerlo entero, y uno lleno de emojis se lee como
    publicidad."""
    instrucciones = build_agent_registry().get("recepcionista").instructions

    assert "*negrilla*" in instrucciones
    assert "Emojis con medida" in instrucciones
