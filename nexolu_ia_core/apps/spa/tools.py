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

Las del bot de WhatsApp no son `WriteTool`, y eso es una decision del
CANAL: una escritura crea un borrador y le dice al modelo "la tarjeta ya se
le mostro al usuario, invitalo a confirmar ahi". En WhatsApp no hay tarjeta
-- la clienta diria "si" y el modelo generaria otro borrador, en bucle. Aca
la confirmacion ocurre en palabras, y el prompt la exige.

El panel del Spa si tiene chat con tarjetas (el agente `administrador`):
sus herramientas de lectura van con permiso y `bloquear_horario` si es una
`WriteTool`.
"""
from __future__ import annotations

from nexolu_ia_core.core.tools.base import Tool, WriteTool
from nexolu_ia_core.core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="guardar_contacto",
            description=(
                "Guarda el nombre de la persona que escribe, asociado a su numero. "
                "Llamala en cuanto sepas como se llama: sin ficha el negocio pierde "
                "el contacto si la conversacion no termina en cita. Tambien sirve "
                "para CORREGIR: si te dice 'soy Valentina, no Mateo', o el nombre "
                "que tienes parece de perfil de WhatsApp (un punto, emojis, un "
                "negocio), guarda el que ella te diga. Pero NO esperes a tener el "
                "nombre para mirar la agenda: si ya sabes que quiere y que dia, en "
                "el mismo turno llama tambien a `disponibilidad`."
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
                "que se puede reservar. Usala antes de proponer precios. Y usala "
                "SIEMPRE que estes a punto de preguntarle a ella algo del "
                "catalogo: que servicios hay, como se llama lo que quiere, si "
                "'las manitos' es manicure, cuanto se demora, si existe tal "
                "cosa. Ella no se sabe el catalogo -- preguntarselo es hacerle "
                "hacer tu trabajo, y muchas veces tampoco sabe la respuesta. Es "
                "gratis y no compromete a nada: mirar primero, preguntar "
                "despues."
            ),
            parameters={"type": "object", "properties": {}},
        )
    )

    registry.register(
        Tool(
            name="disponibilidad",
            description=(
                "Horas libres en una fecha, con quien atiende cada una. Es la "
                "UNICA fuente de disponibilidad: nunca supongas que una hora "
                "esta libre. LLAMALA APENAS sepas que quiere y que dia, en el "
                "mismo turno: no hace falta saber su nombre ni que te confirme "
                "nada para MIRAR. Si quiere VARIOS servicios en la misma visita "
                "('manos y pies'), mandalos todos en `servicios` -- se agendan "
                "como UNA cita encadenada, no como dos."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "servicio": {
                        "type": "string",
                        "description": (
                            # Con la eñe de verdad: la clienta escribe "uñas",
                            # y con el ejemplo en "unas" el modelo no ataba
                            # una cosa con la otra -- preguntaba "¿que
                            # servicio de uñas?" en vez de mandarlo.
                            # La instruccion principal va entera y seguida; lo
                            # de "Muestrame mas servicios" al final. Metida en
                            # medio, separaba "mandalo como lo dijo" de "nunca
                            # preguntes que servicio", y el modelo volvio a
                            # preguntar (0/3 en la evaluacion).
                            "Un solo servicio. Mandalo COMO LO DIJO ELLA: 'las "
                            "manitos', 'las uñas', 'hacerme las uñas', 'los "
                            "pieses', 'un retoque', 'arreglarme las manos'. El "
                            "sistema lo traduce al catalogo, y si da para varios le "
                            "manda los nombres reales para que TOQUE uno. Nunca le "
                            "preguntes '¿que servicio quieres?': no tiene por que "
                            "saberse como lo llamamos nosotros. (Si contesta "
                            "'Muéstrame más servicios', la ultima fila de una "
                            "lista larga, mandame esas mismas palabras.)"
                        ),
                    },
                    "servicios": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Varios servicios, tambien como los diga ella. Con "
                            "`juntas` en false (o sin el): UNA persona, uno despues "
                            "del otro ('manos y pies'). Con `juntas` en true: VARIAS "
                            "personas a la misma hora, un servicio por cada una."
                        ),
                    },
                    "juntas": {
                        "type": "boolean",
                        "description": (
                            "true cuando son VARIAS PERSONAS al tiempo (ella y su hija). "
                            "Necesita una profesional libre por cada una, asi que puede "
                            "haber menos horas."
                        ),
                    },
                    "fecha": {
                        "type": "string",
                        "description": (
                            "El dia TAL COMO lo dijo: 'hoy', 'manana', 'el lunes', "
                            "'el jueves en ocho' o YYYY-MM-DD. NO lo conviertas tu: "
                            "la cuenta la hace el sistema, que sabe que dia es hoy."
                        ),
                    },
                    "franja": {
                        "type": "string",
                        "enum": ["manana", "tarde", "noche"],
                        "description": "Si dijo una franja ('en la tarde'), mandala y el sistema filtra",
                    },
                    "empleado": {"type": "string", "description": "Opcional: con quien"},
                    "sede": {"type": "string", "description": "Solo si el negocio tiene varias"},
                    "para_quien": {
                        "type": "string",
                        "description": (
                            "Si la visita es para OTRA persona ('es para mi mama'), su "
                            "nombre. Mandalo desde que lo sepas: queda guardado con el "
                            "pedido y la reserva lo recibe aunque confirme tocando un boton."
                        ),
                    },
                    "nombres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Con `juntas`: como se llama cada persona, en el mismo orden que `servicios`.",
                    },
                },
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
                "confirmado servicio, fecha y hora en la conversacion. Varios "
                "servicios en `servicios` quedan como UNA sola cita, uno "
                "despues del otro -- nunca digas que hay que agendarlos por "
                "separado. Si la persona YA tiene una cita del mismo servicio, "
                "la herramienta no agenda: te devuelve esa cita y la pregunta "
                "que debes hacer (mover con reagendar_cita, o repetir con "
                "otra_mas=true). Para MOVER una cita nunca uses esta "
                "herramienta: usa reagendar_cita."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "servicio": {"type": "string", "description": "Un solo servicio"},
                    "servicios": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Varios servicios: una cadena para UNA persona, o uno por "
                            "cada persona si `juntas` es true."
                        ),
                    },
                    "juntas": {
                        "type": "boolean",
                        "description": "true = VARIAS personas a la misma hora (dos citas)",
                    },
                    "nombres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Solo con `juntas`: como se llama cada una, en el mismo orden "
                            "que `servicios`. El local necesita saber a quien atiende en "
                            "cada silla."
                        ),
                    },
                    "fecha": {
                        "type": "string",
                        "description": "El dia tal como lo dijo ('el lunes', 'manana') o YYYY-MM-DD",
                    },
                    "hora": {"type": "string", "description": "HH:MM (el `hora_24` de disponibilidad)"},
                    "empleado": {"type": "string", "description": "Opcional"},
                    "sede": {"type": "string", "description": "Obligatorio si hay varias"},
                    "cliente": {"type": "string", "description": "Su nombre, si aun no lo tienes"},
                    "para_quien": {
                        "type": "string",
                        "description": "Solo si la visita NO es para quien escribe (una hija, una amiga)",
                    },
                    "otra_mas": {
                        "type": "boolean",
                        "description": (
                            "true SOLO cuando la herramienta aviso que ya tiene una cita "
                            "del mismo servicio y la persona respondio que quiere OTRA "
                            "aparte (no moverla)."
                        ),
                    },
                },
                "required": ["fecha", "hora"],
            },
        )
    )

    registry.register(
        Tool(
            name="cancelar_cita",
            description=(
                "Cancela una cita de la persona. El id sale de `mis_citas`. "
                "Pregunta cual antes de cancelar si tiene mas de una. Si faltan "
                "pocas horas, la herramienta NO cancela y te devuelve "
                "`requiere_multa` con el aviso: diselo tal cual y, solo si "
                "responde que si, vuelve a llamarla con acepta_multa=true."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cita_id": {"type": "integer"},
                    "motivo": {"type": "string"},
                    "acepta_multa": {
                        "type": "boolean",
                        "description": "true SOLO despues de avisarle la multa por cancelacion tardia y que dijera que si",
                    },
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

    # -- Las del panel ---------------------------------------------------
    # De quien administra, nunca de la clienta: el Spa las marca
    # allowsCustomers=false y responde 403 si llegan por WhatsApp. Aca
    # llevan su permiso para que el Core ni siquiera se las ofrezca al
    # modelo sin el.

    registry.register(
        Tool(
            name="resumen_del_dia",
            description=(
                "Como le fue al negocio un dia: lo vendido en servicios, por medio de "
                "pago, comisiones, gastos, productos, las citas del dia (completadas, "
                "canceladas, sin cobrar), lo de cada persona y cuantas citas ENTRARON "
                "ese dia por cada canal (pagina web, WhatsApp, panel). Para 'cuanto "
                "vendi hoy', 'como nos fue ayer', 'mi resumen del dia'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fecha": {"type": "string", "description": "Como la dijeron: 'hoy', 'ayer', 'el viernes', o YYYY-MM-DD. Vacio = hoy."},
                },
            },
            required_permission="reportes.ver",
        )
    )

    registry.register(
        Tool(
            name="ventas",
            description=(
                "Ventas de un periodo: total, servicios hechos, ticket promedio, lo de "
                "cada persona, por medio de pago y los SERVICIOS MAS HECHOS. Para 'que "
                "servicios se hicieron mas esta semana', 'cuanto vendio Marcela este "
                "mes', 'ventas de la semana pasada'. Se cuenta por fecha de cobro."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "periodo": {"type": "string", "description": "'hoy', 'ayer', 'esta semana', 'semana pasada', 'este mes', 'mes pasado', 'este año'. Si lo dijeron asi, usa esto y no desde/hasta."},
                    "desde": {"type": "string", "description": "Inicio si dieron fechas concretas ('1 de septiembre' o YYYY-MM-DD)."},
                    "hasta": {"type": "string", "description": "Fin si dieron fechas concretas."},
                    "persona": {"type": "string", "description": "Solo lo de esta persona del equipo, si la nombraron."},
                },
            },
            required_permission="reportes.ver",
        )
    )

    registry.register(
        Tool(
            name="agenda",
            description=(
                "Las citas de un dia, con hora, clienta, servicio, con quien, estado y por "
                "donde entro. Para 'que citas hay manana', 'que tiene Alejandra el viernes'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fecha": {"type": "string", "description": "Como la dijeron. Vacio = hoy."},
                    "persona": {"type": "string", "description": "Solo las de esta persona, si la nombraron."},
                },
            },
            required_permission="citas.ver_todas",
        )
    )

    registry.register(
        Tool(
            name="clientas_sin_agendar",
            description=(
                "Las clientas que escriben por WhatsApp pero no agendan: cuantos mensajes "
                "mandaron, cuando fue el ultimo y su ultima visita. Descarta a quien agendo "
                "en ese tiempo o tiene cita por venir. Son ventas que se escaparon: a esas "
                "vale la pena escribirles."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "minimum": 1, "maximum": 180, "description": "Cuantos dias hacia atras mirar. Por defecto 30."},
                },
            },
            required_permission="clientes.ver",
        )
    )

    registry.register(
        WriteTool(
            name="bloquear_horario",
            description=(
                "Bloquea horas de una persona del equipo en una fecha o un rango de fechas: "
                "en ese tiempo no sale disponible ni en el bot, ni en la web, ni al agendar. "
                "Para 'bloqueale a Alejandra el viernes de 5 a 6', 'Marcela no viene el lunes' "
                "(todo el dia). Crea un borrador que la persona confirma en la tarjeta."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "persona": {"type": "string", "description": "A quien se le bloquea."},
                    "desde": {"type": "string", "description": "Fecha como la dijeron ('el viernes', 'manana') o YYYY-MM-DD."},
                    "hasta": {"type": "string", "description": "Ultima fecha si es un rango. Vacio = solo ese dia."},
                    "hora_inicio": {"type": "string", "description": "HH:MM en 24 horas ('17:00'). Vacio = todo el dia."},
                    "hora_fin": {"type": "string", "description": "HH:MM en 24 horas ('18:00')."},
                    "todo_el_dia": {"type": "boolean"},
                    "motivo": {"type": "string", "description": "Opcional: 'Cita medica', 'Vacaciones'..."},
                },
                "required": ["persona", "desde"],
            },
            required_permission="horarios.gestionar",
            draft_type="bloqueo",
            summarize=lambda v: (
                f"Bloquear a {v.get('persona')} el {v.get('desde')}"
                + (f" hasta el {v.get('hasta')}" if v.get("hasta") else "")
                + (
                    " todo el dia"
                    if v.get("todo_el_dia") or not v.get("hora_inicio")
                    else f" de {v.get('hora_inicio')} a {v.get('hora_fin')}"
                )
            ),
            fields=lambda _context: {
                "persona": {"type": "string", "label": "Persona"},
                "desde": {"type": "string", "label": "Desde"},
                "hasta": {"type": "string", "label": "Hasta"},
                "hora_inicio": {"type": "string", "label": "Hora inicio (HH:MM)"},
                "hora_fin": {"type": "string", "label": "Hora fin (HH:MM)"},
                "motivo": {"type": "string", "label": "Motivo"},
            },
        )
    )

    return registry
