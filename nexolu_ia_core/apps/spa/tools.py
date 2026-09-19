"""Herramientas del Spa.

Estas son las que el Spa IMPLEMENTA de verdad en su
`POST /api/ai/tools/invoke` (ver `App\\Ai\\Registry` en nexolu-spa-api). El
catalogo de aca y el de alla tienen que coincidir: una herramienta declarada
que la app no implementa hace que el modelo la intente, reciba un 404 y le
conteste a la clienta con una disculpa por algo que nunca iba a funcionar.

Dos ausencias deliberadas:

- `clientes`: enumerar la base de clientas del negocio por un chat es
  exactamente lo que no puede pasar. El Spa responde 404 a proposito, asi
  que declararla solo produciria intentos fallidos.
- `empleados`: quien atiende ya viaja dentro de `disponibilidad`, que es
  donde importa ("a las 10 con Maria"). Una lista suelta del equipo no
  ayuda a agendar.

Ninguna es `WriteTool`, y eso es una decision del CANAL: una escritura crea
un borrador y le dice al modelo "la tarjeta ya se le mostro al usuario,
invitalo a confirmar ahi". En WhatsApp no hay tarjeta -- la clienta diria
"si" y el modelo generaria otro borrador, en bucle. Aca la confirmacion
ocurre en palabras, y el prompt la exige. El dia que el panel del Spa tenga
un chat con tarjetas, ese canal necesitara sus propias herramientas de
escritura.
"""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="guardar_contacto",
            description=(
                "Guarda el nombre de la persona que escribe, asociado a su numero. "
                "Llamala en cuanto sepas como se llama, ANTES de buscar horas: sin "
                "ficha el negocio pierde el contacto si la conversacion no termina "
                "en cita."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Como se llama quien escribe"},
                },
                "required": ["nombre"],
            },
        )
    )

    registry.register(
        Tool(
            name="servicios",
            description=(
                "Catalogo del negocio: nombre, precio y duracion de cada servicio "
                "que se puede reservar. Usala antes de proponer precios."
            ),
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="disponibilidad",
            description=(
                "Horas libres de un servicio en una fecha, con quien atiende cada "
                "una. Es la UNICA fuente de disponibilidad: nunca supongas que una "
                "hora esta libre."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "servicio": {"type": "string", "description": "Nombre del servicio"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "empleado": {"type": "string", "description": "Opcional: con quien"},
                    "sede": {"type": "string", "description": "Obligatorio si el negocio tiene varias"},
                },
                "required": ["servicio", "fecha"],
            },
        )
    )

    registry.register(
        Tool(
            name="mis_citas",
            description=(
                "Las citas proximas de la persona con la que estas hablando. No "
                "recibe a quien: siempre son las suyas."
            ),
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="crear_cita",
            description=(
                "Agenda la cita. Llamala SOLO despues de que la persona haya "
                "confirmado servicio, fecha y hora en la conversacion."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "servicio": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "hora": {"type": "string", "description": "HH:MM"},
                    "empleado": {"type": "string", "description": "Opcional"},
                    "sede": {"type": "string", "description": "Obligatorio si hay varias"},
                    "cliente": {"type": "string", "description": "Su nombre, si aun no lo tienes"},
                    "para_quien": {
                        "type": "string",
                        "description": "Solo si la visita NO es para quien escribe (una hija, una amiga)",
                    },
                },
                "required": ["servicio", "fecha", "hora"],
            },
        )
    )

    registry.register(
        Tool(
            name="cancelar_cita",
            description=(
                "Cancela una cita de la persona. El id sale de `mis_citas`. "
                "Pregunta cual antes de cancelar si tiene mas de una."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cita_id": {"type": "integer"},
                    "motivo": {"type": "string"},
                },
                "required": ["cita_id"],
            },
        )
    )

    registry.register(
        Tool(
            name="reagendar_cita",
            description=(
                "Mueve una cita existente a otra fecha/hora. El id sale de "
                "`mis_citas`. Confirma la hora nueva con `disponibilidad` antes "
                "de llamarla. Siempre mejor que cancelar y volver a crear: la "
                "persona no pierde su turno si la hora nueva resulta ocupada."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cita_id": {"type": "integer"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                    "hora": {"type": "string", "description": "HH:MM"},
                    "empleado": {"type": "string", "description": "Opcional, si quiere cambiar de persona"},
                },
                "required": ["cita_id", "fecha", "hora"],
            },
        )
    )

    registry.register(
        Tool(
            name="ofrecer_opciones",
            description=(
                "Le manda a la persona opciones que puede TOCAR (botones si son "
                "3 o menos, lista si son mas) en vez de hacerla escribir. Usala "
                "SIEMPRE que le ofrezcas horas, servicios o un si/no: tocar es "
                "un gesto, escribir una hora es un esfuerzo -- y ahi es donde se "
                "pierde la cita. IMPORTANTE: esta herramienta YA le envia el "
                "mensaje; despues de llamarla responde con una cadena vacia, "
                "porque cualquier texto tuyo le llegaria repetido."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mensaje": {
                        "type": "string",
                        "description": "Lo que va escrito arriba de las opciones",
                    },
                    "opciones": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 24},
                        "description": "Maximo 10, cortas ('3 pm', 'Semipermanente', 'Si')",
                    },
                    "boton": {
                        "type": "string",
                        "description": "Solo si son 4 o mas: el texto que abre la lista ('Ver horas')",
                    },
                },
                "required": ["mensaje", "opciones"],
            },
        )
    )

    registry.register(
        Tool(
            name="hablar_con_persona",
            description=(
                "Avisa al equipo del negocio que esta conversacion necesita a "
                "alguien de carne y hueso, y TE CALLA a ti hasta que respondan. "
                "Llamala cuando lo pidan ('quiero hablar con alguien', 'me "
                "atiende una persona?'), cuando se quejen o reclamen, y cuando "
                "algo se salga de lo que puedes resolver (precios especiales, "
                "un problema con un trabajo hecho, algo delicado). Es preferible "
                "llamarla de mas que dejar a alguien molesto hablandole a un bot."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "motivo": {
                        "type": "string",
                        "description": "Que necesita, en una linea, para quien vaya a atender",
                    },
                },
                "required": ["motivo"],
            },
        )
    )

    return registry
