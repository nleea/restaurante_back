"""Respuestas automáticas: el saludo, el enlace con token, los avisos de estado y las FAQs.

Cero LLM. Todo esto es texto determinista sobre datos que el sistema ya tiene —los horarios
de la sede y el ciclo de vida del pedido— y por eso cuesta cero tokens. Es la parte que un
dueño de restaurante enseña como "el bot de WhatsApp".

Tres reglas sostienen el módulo:

1. **El saludo es incondicional y sale una vez.** Cualquier mensaje entrante sobre una
   conversación `new` lo dispara. Nada de detectar intención: "quiero pedir", "buenas" y "?"
   merecen la misma primera respuesta, y una lista de palabras clave es una fábrica de bugs.
2. **Nunca se inicia una conversación.** Todo sale por el gateway guardado del canal, que
   rechaza escribir a quien no escribió primero. Nada de aquí puede empezar una charla.
3. **Cada mensaje automático se emite una sola vez**, y eso lo garantiza una constraint de
   unicidad en la base de datos, no un `if ya_enviamos`.

Y una aclaración que hace falta desde que existen las FAQs (`answer_faq`), porque parecen
contradecir la regla 1: **no la contradicen, y el matiz importa.** La regla 1 habla del SALUDO —
decidir la PRIMERA respuesta por intención—, y eso sigue prohibido: el saludo no lee el texto.
Las FAQs leen el texto DESPUÉS del saludo, donde antes no había ninguna respuesta, y sólo son
defendibles por tres propiedades que la regla 1 no tenía a mano:

- coincidencia por palabra o frase completa, insensible al plural pero **sin *stemming*** — es lo
  que impide que `pago` encuentre "ya pagué y no me llegó";
- silencio si el contacto tiene un pedido vivo, o si pide una persona — es lo que impide que
  `direccion` encuentre "mi dirección es la calle 5";
- contestar **no cambia el estado de la conversación ni la saca de la bandeja**, así que una
  coincidencia equivocada es un mensaje bochornoso y no un cliente perdido.

Quitar cualquiera de las tres devuelve el módulo a la fábrica de bugs que la regla 1 describe.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from restaurante.modules.business.application.clock import weekday_and_minute
from restaurante.modules.business.domain.hours import (
    HoursWindow,
    closing_at,
    is_open_at,
    next_opening,
)
from restaurante.modules.messaging.domain.entities import (
    AutoreplySettings,
    FaqEntry,
    QuickReply,
    WhatsAppConversation,
)
from restaurante.modules.messaging.domain.faq import (
    asks_for_a_person,
    first_match,
    reserved_words_in,
)
from restaurante.modules.messaging.domain.ports import (
    BusinessIdentity,
    MessagingRepository,
    OrderContext,
    WhatsAppGateway,
)
from restaurante.modules.messaging.domain.quick_reply import validate_quick_replies
from restaurante.modules.messaging.domain.templates import (
    AWAITING_PAYMENT_PLACEHOLDERS,
    FAQ_PLACEHOLDERS,
    GREETING_PLACEHOLDERS,
    ORDER_PLACEHOLDERS,
    find_placeholders,
    format_hours_line,
    format_next_opening,
    render,
    unknown_placeholders,
)
from restaurante.modules.messaging.infrastructure.models import (
    EMISSION_FAQ,
    EMISSION_GREETING,
    EMISSION_PAYMENT_REQUEST,
    EMISSION_STATUS,
)
from restaurante.shared.config import get_settings
from restaurante.shared.customer_channel.ports import (
    CUSTOMER_STATE_ASSIGNED,
    CUSTOMER_STATE_AWAITING_PROOF,
    CUSTOMER_STATE_CANCELLED,
    CUSTOMER_STATE_DELIVERED,
    CUSTOMER_STATE_ON_THE_WAY,
    CUSTOMER_STATE_ORDER_RECEIVED,
    CUSTOMER_STATE_READY,
    CUSTOMER_STATES,
    EMISSION_FAILED,
    EMISSION_NO_CONTACT,
    EMISSION_SENT,
    ChannelContact,
    EmissionOutcome,
)
from restaurante.shared.domain.errors import ValidationError
from restaurante.shared.domain.order_label import order_label
from restaurante.shared.links import tenant_base_url

logger = logging.getLogger(__name__)

# Estado al que pasa una conversación tras saludarla. Es lo que impide saludar dos veces.
STATUS_GREETED = "greeted"
STATUS_NEW = "new"

# Textos por defecto. Un tenant que enciende el saludo sin escribir nada obtiene algo
# presentable en vez de un mensaje vacío.
# Se saluda con el nombre del NEGOCIO, no con el de la sucursal. Es lo que el dueño rellena
# primero en el Perfil del negocio y es como el cliente conoce el sitio; la sucursal se llama
# "Main Branch" hasta que alguien la renombra, y "Bienvenido a Main Branch" es exactamente el
# mensaje que hace que un restaurante no encienda esto. Un tenant con varias sedes añade
# `{branch_name}` al texto — con una sola, decirlo sobra.
DEFAULT_GREETING_OPEN = (
    "¡Hola! Bienvenido a {business_name}. 👋\n\n"
    "Mira nuestra carta y haz tu pedido aquí:\n{menu_link}"
)
DEFAULT_GREETING_CLOSED = (
    "¡Hola! Bienvenido a {business_name}. 👋\n\n"
    "Ahora mismo estamos cerrados — abrimos {next_opening}.\n\n"
    "Puedes ir mirando la carta aquí:\n{menu_link}"
)
# Se añade sólo si el tenant tiene el asistente Y el negocio está ABIERTO. El saludo NUNCA
# debe ofrecer algo que no vaya a responder, y fuera de horario el asistente no responde: el
# horario lo apaga (`assistant/application/use_cases/conversation.py`). Un saludo de cerrado
# que ofrezca "escribe 1" deja al cliente escribiendo un 1 a las once de la noche al que no
# contesta ni el bot ni una persona — que es exactamente lo que la oferta prometía evitar.
ASSISTANT_OFFER = "\n\nEscribe *1* si prefieres que te atienda nuestro asistente."

# ¿Existe el asistente conversacional? Hoy no, para nadie: lo trae `assistant-core` (fase 4).
#
# Vive aquí y viaja en la respuesta del API —en vez de ser una constante del front— porque
# encenderlo tiene que ser un cambio de servidor. Si la pantalla lo decidiera por su cuenta,
# el día que el asistente exista habría que desplegar el cliente para que el dueño pudiera
# ofrecerlo, y el día que un tenant lo pierda su saludo seguiría prometiéndolo.
def assistant_available() -> bool:
    """¿Puede este DESPLIEGUE ofrecer el asistente?

    Pasó de constante a función con `assistant-core`: ya no es "no existe para nadie", es
    "existe si hay credencial de proveedor y el interruptor global está en marcha". Sigue
    siendo una decisión de servidor —encenderlo no puede exigir desplegar el cliente— y
    sigue sin ser una promesa por tenant: quién lo tiene contratado lo decide su derecho, y
    eso se comprueba antes de meter a nadie en modo bot.
    """
    settings = get_settings()
    return bool(settings.assistant_api_key) and not settings.assistant_kill_switch

_TOKEN_BYTES = 24

# Qué transiciones internas le hablan al cliente, de fábrica.
#
# Cuatro encendidas, dos apagadas. No es una lista arbitraria: cada mensaje automático
# gasta cuota del número y ocho avisos por pedido es exactamente la conducta que hace que
# WhatsApp marque una cuenta —y que el cliente silencie el chat—. `ready` y `assigned` se
# dejan disponibles pero apagados porque sólo tienen sentido en negocios concretos (recoger
# en tienda; flota con seguimiento), y encenderlos es una decisión del dueño.
DEFAULT_STATUS_MAPPING: dict[str, dict[str, object]] = {
    # El acuse lleva el detalle de lo pedido: es el único mensaje que el cliente relee para
    # comprobar que le entendimos, y "Total: $46.000" a secas le obliga a confiar en un
    # número que no puede verificar. Los demás estados NO lo llevan — repetir la lista en
    # cada aviso convierte el chat en un catálogo.
    CUSTOMER_STATE_ORDER_RECEIVED: {
        "enabled": True,
        "text": (
            "¡Recibimos tu pedido *{order_number}* en {business_name}! 🧾\n\n"
            "{order_items}\n"
            "Total: {order_total}.\n\n"
            "Te avisamos cuando vaya en camino."
        ),
    },
    # El acuse de un pedido que nace debiendo. **Sustituye** al de arriba, nunca se suma: dos
    # mensajes por el mismo hecho es el volumen de salida que hace que WhatsApp mire un número, y
    # el techo de cuatro por pedido es la defensa principal de este módulo.
    #
    # El texto no EXIGE el comprobante, y es deliberado: cuando este aviso sale, el cliente puede
    # haberlo adjuntado ya en el checkout (la subida es una llamada posterior a crear el pedido).
    # Pedirle lo que acaba de mandar se lee como que no llegó.
    CUSTOMER_STATE_AWAITING_PROOF: {
        "enabled": True,
        "text": (
            "¡Recibimos tu pedido *{order_number}* en {business_name}! 🧾\n\n"
            "{order_items}\n"
            "Total: {order_total}.\n\n"
            "Lo tenemos guardado y entra a cocina en cuanto confirmemos tu pago. "
            "Si tienes el comprobante a mano, puedes mandarlo por aquí."
        ),
    },
    CUSTOMER_STATE_READY: {
        "enabled": False,
        "text": (
            "Tu pedido *{order_number}* ya está listo para recoger en "
            "{business_name}. 🛎️"
        ),
    },
    CUSTOMER_STATE_ASSIGNED: {
        "enabled": False,
        "text": "Tu pedido *{order_number}* ya tiene domiciliario asignado.",
    },
    CUSTOMER_STATE_ON_THE_WAY: {
        "enabled": True,
        "text": "Tu pedido *{order_number}* va en camino. 🛵",
    },
    CUSTOMER_STATE_DELIVERED: {
        "enabled": True,
        "text": "Tu pedido *{order_number}* fue entregado. ¡Gracias! 🙌",
    },
    CUSTOMER_STATE_CANCELLED: {
        "enabled": True,
        "text": (
            "Tu pedido *{order_number}* fue cancelado.\n"
            "Si crees que es un error, respóndenos por aquí."
        ),
    },
}


# Las cuatro preguntas que todo restaurante recibe, con los gatillos que la gente escribe de
# verdad. **Nacen apagadas**, y eso no es timidez: el comentario del modelo de ajustes ya fija la
# regla ("apagado por defecto: instalar este change no puede cambiar el comportamiento de nadie"),
# y encender cuatro respuestas automáticas en un número que ya está operando es justo lo que nadie
# pidió. El dueño las lee en la pantalla y las enciende.
#
# Los gatillos están escritos para coincidencia por PALABRA COMPLETA, que es lo que hace que la
# lista de un brief ingenuo no sirva tal cual:
#   · `pago` a secas NO está, y es la corrección más importante del conjunto: es la palabra del
#     reclamo ("ya pagué", "el pago no me llegó"), no la de la pregunta.
#   · los plurales tampoco: los cubre `plural_variants`.
#   · `direccion` SÍ está, pese a "mi dirección es la calle 5", porque de eso se encarga el gate
#     de pedido vivo y sin ella la FAQ pierde la forma más común de preguntar.
SUGGESTED_FAQS: tuple[FaqEntry, ...] = (
    FaqEntry(
        id="faq-location",
        name="Ubicación",
        triggers=["ubicacion", "direccion", "donde estan", "donde queda", "como llego"],
        text="Estamos en {branch_address}. ¡Te esperamos! 📍",
        enabled=False,
    ),
    FaqEntry(
        id="faq-hours",
        name="Horario",
        triggers=[
            "horario",
            "a que hora abren",
            "a que hora cierran",
            "hasta que hora",
            "estan abiertos",
        ],
        # `{hours_line}` y no `{next_opening}`: el segundo contesta la mitad del día con la
        # apertura de mañana.
        text="Estamos {hours_line}. 🕒",
        enabled=False,
    ),
    FaqEntry(
        id="faq-payment",
        name="Métodos de pago",
        triggers=[
            "metodos de pago",
            "medios de pago",
            "como pago",
            "aceptan tarjeta",
            "aceptan nequi",
        ],
        # Texto libre a propósito: no hay una fuente canónica de métodos de pago, y un marcador
        # que se desincronice de lo que Caja acepta de verdad es un pasivo.
        text="Recibimos efectivo, Nequi y tarjeta. Si pagas por transferencia, mándanos el "
        "comprobante por aquí. 💳",
        enabled=False,
    ),
    FaqEntry(
        id="faq-delivery",
        name="Domicilios",
        triggers=["domicilio", "hacen entregas", "hacen envios", "delivery", "llevan a"],
        text="Sí, hacemos domicilios. Pide aquí y te decimos el costo del envío según tu "
        "dirección:\n{menu_link}",
        enabled=False,
    ),
)


# Estados que terminan el hilo, igual que el botón "Cerrar" de la bandeja.
#
# Un pedido entregado es una conversación acabada: dejarla abierta hace que la bandeja
# acumule hilos que nadie va a contestar y que el siguiente pedido del mismo cliente se
# cuele en el chat de ayer. Cerrar no borra nada —el histórico se ve con `include_closed`—
# y el cliente no se entera: la próxima vez que escriba se le abre un hilo nuevo y vuelve a
# recibir el saludo con el enlace de la carta, que es justo lo que quiere quien vuelve.
#
# `cancelled` NO cierra a propósito: un pedido cancelado es exactamente la conversación que
# el cliente continúa ("¿por qué me lo cancelaron?") y cerrarla es colgarle el teléfono.
CLOSING_STATES: frozenset[str] = frozenset({CUSTOMER_STATE_DELIVERED})


class AutoreplyService:
    def __init__(
        self,
        repo: MessagingRepository,
        gateway: WhatsAppGateway,
        storefront_base_url: str = "",
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        # Dominio público de la carta SIN subdominio; el slug del tenant se antepone.
        self._storefront_base_url = storefront_base_url

    # --- Ajustes -------------------------------------------------------------
    async def settings_for(self, tenant_id: uuid.UUID) -> AutoreplySettings:
        """Los ajustes del tenant, o los de fábrica (todo apagado) si nunca los tocó."""
        stored = await self._repo.get_autoreply_settings(tenant_id)
        return stored or AutoreplySettings(tenant_id=tenant_id)

    async def save_settings(self, settings: AutoreplySettings) -> AutoreplySettings:
        """Valida los textos y guarda. Un marcador desconocido es un 422, no un envío roto.

        La validación es AL GUARDAR a propósito: descubrir a las 8pm que `{cliente}` no
        existe, con un cliente esperando, no le sirve a nadie. Aquí el dueño está mirando
        la pantalla y puede corregirlo.
        """
        _reject_unknown(settings.greeting_open_text, GREETING_PLACEHOLDERS, "saludo")
        _reject_unknown(
            settings.greeting_closed_text, GREETING_PLACEHOLDERS, "saludo (cerrado)"
        )
        _reject_unknown(
            settings.greeting_awaiting_payment_text,
            AWAITING_PAYMENT_PLACEHOLDERS,
            "saludo (esperando pago)",
        )
        for state, entry in settings.status_mapping.items():
            if state not in CUSTOMER_STATES:
                raise ValidationError(f"Estado de pedido desconocido: {state}")
            if isinstance(entry, dict):
                _reject_unknown(str(entry.get("text") or ""), ORDER_PLACEHOLDERS, state)
        if settings.idle_hours < 1 or settings.token_lifetime_hours < 1:
            raise ValidationError("Las ventanas se miden en horas y mínimo son 1.")
        if settings.faqs is not None:
            _validate_faqs(settings.faqs)
        if settings.quick_replies is not None:
            validate_quick_replies(settings.quick_replies)
        return await self._repo.upsert_autoreply_settings(settings)

    async def quick_replies_for(self, tenant_id: uuid.UUID) -> list[QuickReply]:
        """Las plantillas GUARDADAS de un tenant. Sin lista, ninguna.

        Aquí es donde se separa de `faqs_for`, y es deliberado: `None` **no** se cambia por las
        sugeridas. Las sugeridas existen para el editor, donde el dueño las adopta y las guarda;
        devolverlas por aquí las metería en el compositor de un mesero sin que nadie las haya
        aprobado, que es poner palabras en boca del negocio.
        """
        settings = await self.settings_for(tenant_id)
        return settings.quick_replies or []

    async def faqs_for(self, tenant_id: uuid.UUID) -> list[FaqEntry]:
        """Las FAQs vigentes de un tenant. Sin lista guardada, las sugeridas (apagadas).

        Aquí está la diferencia entre `None` y `[]`, y es la razón de que la columna sea nullable:
        `None` es "nunca las tocó" y se le ofrecen las sugeridas; `[]` es "decidió que ninguna" y
        se respeta. Fusionar lo guardado sobre las sugeridas —como hace `status_mapping`— haría
        que una FAQ borrada volviera en la siguiente lectura.
        """
        settings = await self.settings_for(tenant_id)
        return list(SUGGESTED_FAQS) if settings.faqs is None else settings.faqs

    # --- Saludo --------------------------------------------------------------
    async def greet_if_new(
        self, conversation: WhatsAppConversation, contact_phone: str
    ) -> bool:
        """Saluda una conversación recién abierta. True si se envió algo.

        Incondicional respecto al contenido: da igual si el cliente escribió "hola", "quiero
        pedir" o mandó una foto. Intentar adivinar intención sin un modelo produce un sistema
        que se equivoca de formas impredecibles, y el saludo es barato.
        """
        if conversation.status != STATUS_NEW:
            return False
        settings = await self.settings_for(conversation.tenant_id)
        if not settings.greeting_enabled:
            # Apagado: la conversación sigue `new` — no se marca como saludada algo que
            # nadie saludó.
            return False

        if not self._storefront_base_url:
            # Sin base pública, el enlace saldría como "/store/centro?t=…": una ruta
            # relativa que por WhatsApp no es clicable. Mandar eso es peor que no saludar,
            # así que se calla y se deja constancia de QUÉ falta.
            logger.warning(
                "Saludo no enviado: falta STOREFRONT_BASE_URL, el enlace a la "
                "carta saldría relativo y el cliente no podría abrirlo."
            )
            return False

        # La constraint manda: si otro proceso ya reclamó este saludo, aquí no se envía.
        won = await self._repo.try_claim_emission(
            conversation.tenant_id,
            conversation.branch_id,
            kind=EMISSION_GREETING,
            conversation_id=conversation.id,
        )
        if not won:
            return False

        text = await self.render_greeting(conversation, settings)
        if not await self._send_and_record(conversation, contact_phone, text):
            return False
        await self._repo.update_conversation_status(
            conversation.tenant_id, conversation.id, STATUS_GREETED
        )
        return True

    async def _send_and_record(
        self,
        conversation: WhatsAppConversation,
        contact_phone: str,
        text: str,
        *,
        employee_id: uuid.UUID | None = None,
    ) -> bool:
        """Envía por el gateway guardado y deja el mensaje en el hilo. True si salió.

        Persistir lo enviado es lo que hace legible un hueco: si un aviso no salió, el
        agente lo ve por su ausencia en la conversación y no tiene que adivinar.
        """
        session = await self._repo.get_session_for_branch(
            conversation.tenant_id, conversation.branch_id
        )
        if session is None:
            logger.warning(
                "Mensaje automático no enviado: la sucursal %s no tiene número vinculado",
                conversation.branch_id,
            )
            return False
        try:
            await self._gateway.send_text(session, contact_phone, text)
        except Exception:  # noqa: BLE001
            # Un mensaje que no sale no puede tumbar lo que lo disparó —ni la recepción
            # del mensaje del cliente ni la transición del pedido—. Queda el rastro.
            logger.warning("No se pudo enviar el mensaje automático", exc_info=True)
            return False

        await self._repo.add_message(
            conversation.tenant_id,
            conversation.branch_id,
            conversation.id,
            sender_type="employee" if employee_id else "system",
            content=text,
            employee_id=employee_id,
        )
        return True

    async def render_greeting(
        self, conversation: WhatsAppConversation, settings: AutoreplySettings
    ) -> str:
        """El saludo de ESTA sede: su nombre, su enlace y sus horarios."""
        tenant_id = conversation.tenant_id
        branch_id = conversation.branch_id
        identity = await self._repo.business_identity(tenant_id, branch_id)
        windows = [
            HoursWindow(weekday=w, open_minute=o, close_minute=c)
            for w, o, c in await self._repo.branch_hours(tenant_id, branch_id)
        ]
        # Hora LOCAL de la sede, no UTC: los horarios están guardados en hora local, y
        # compararlos con UTC en Colombia (UTC-5) declaraba cerrado un negocio abierto —y,
        # pasadas las 7 de la tarde, consultaba el horario del día siguiente.
        weekday, minute = weekday_and_minute()
        open_now = is_open_at(windows, weekday, minute)

        link = await self.mint_store_link(conversation, settings)
        values = {**_identity_values(identity), "menu_link": link}

        # Tercera variante, y se elige por el ESTADO DEL PEDIDO — nunca por lo que el cliente
        # escribió. Eso es lo que la hace compatible con la regla #1 del módulo: el saludo sigue
        # siendo incondicional respecto al texto (una foto, "hola" y un sticker dan lo mismo).
        #
        # Sin ella, alguien que pidió por la web y manda su comprobante como primer mensaje recibe
        # "Bienvenido, mira nuestra carta 👋" encima del recibo. Y de paso pone el número y el total
        # en el hilo, que es lo que el agente necesita leer sobre la foto.
        awaiting = await self._awaiting_payment_order(conversation, settings.idle_hours)
        if awaiting is not None and settings.greeting_awaiting_payment_text:
            values["order_number"] = order_number(awaiting.order_id)
            values["order_total"] = format_money(awaiting.total)
            return render(settings.greeting_awaiting_payment_text, values)

        if open_now:
            template = settings.greeting_open_text or DEFAULT_GREETING_OPEN
        else:
            template = settings.greeting_closed_text or DEFAULT_GREETING_CLOSED
            opening = format_next_opening(
                next_opening(windows, weekday, minute), weekday
            )
            if opening:
                values["next_opening"] = opening

        text = render(template, values)
        # Con el negocio cerrado, la oferta no sale. Ver `ASSISTANT_OFFER`: fuera de horario
        # no hay quien la atienda, ni el asistente ni una persona.
        if settings.assistant_offer_enabled and open_now:
            text += ASSISTANT_OFFER
        return text

    async def _awaiting_payment_order(
        self, conversation: WhatsAppConversation, idle_hours: int
    ) -> OrderContext | None:
        """El pedido prepago sin pagar de este contacto, si hay uno. Nunca levanta.

        Un fallo aquí cuesta la variante del saludo, no el saludo: se cae a la de
        abierto/cerrado, que es lo que salía antes de que esta variante existiera.

        La ventana es la de inactividad de la conversación, el mismo número que ya usa el gate de
        las FAQs: es la misma pregunta —"¿esto sigue vivo?"— y tenerla configurada dos veces con
        criterios distintos sería tener dos verdades.
        """
        since = datetime.now(UTC) - timedelta(hours=max(1, idle_hours))
        try:
            return await self._repo.unsettled_prepaid_order(
                conversation.tenant_id,
                conversation.whatsapp_contact_id,
                since=since,
            )
        except Exception:  # noqa: BLE001 - una variante perdida no puede costar el saludo
            logger.warning(
                "No se pudo comprobar si el contacto tiene un pedido esperando pago",
                exc_info=True,
            )
            return None

    # --- FAQs por palabra clave ----------------------------------------------
    async def answer_faq(
        self,
        conversation: WhatsAppConversation,
        contact_phone: str,
        contact_id: uuid.UUID,
        text: str,
    ) -> bool:
        """Contesta una pregunta conocida. `True` si salió algo.

        El orden de las comprobaciones ES el diseño, y va de lo más barato a lo más caro:

        1. **Sólo `greeted`.** `new` es del saludo (y el estado se lee antes de saludar, así que
           el primer mensaje nunca llega aquí: saludo + FAQ serían dos automáticos por un
           entrante). `bot` es del asistente, que tiene herramientas y redacta mejor. `human` es
           de quien la reclamó, e interrumpirle es peor que callar.
        2. **Pedir persona, cancelar o devolver.** Cuesta cero y la respuesta ya se sabe.
        3. **Pedido vivo.** Una consulta, y si falla se calla.
        4. **La coincidencia.** Palabra completa, primera de la lista.
        5. **El reclamo de emisión.** Preguntar dos veces lo mismo recibe una respuesta.

        Contestar **no cambia el estado** de la conversación: sigue en `greeted` y sigue en la
        bandeja. Es lo que hace que una coincidencia equivocada sea un mensaje bochornoso y no un
        cliente perdido, y por eso este método puede permitirse un matching tonto.
        """
        if conversation.status != STATUS_GREETED:
            return False
        message = text.strip()
        if not message:
            return False

        if asks_for_a_person(message):
            logger.debug(
                "FAQ callada: el mensaje pide una persona (conversación %s)",
                conversation.id,
            )
            return False

        settings = await self.settings_for(conversation.tenant_id)
        faqs = list(SUGGESTED_FAQS) if settings.faqs is None else settings.faqs
        faq = first_match(faqs, message)
        if faq is None:
            return False

        if await self._has_live_order(conversation, contact_id, settings.idle_hours):
            logger.info(
                "FAQ «%s» callada: el contacto tiene un pedido en curso (conversación %s)",
                faq.name,
                conversation.id,
            )
            return False

        won = await self._repo.try_claim_emission(
            conversation.tenant_id,
            conversation.branch_id,
            kind=EMISSION_FAQ,
            conversation_id=conversation.id,
            detail=faq.id,
        )
        if not won:
            return False

        return await self._send_and_record(
            conversation, contact_phone, await self._render_faq(conversation, faq)
        )

    async def _has_live_order(
        self,
        conversation: WhatsAppConversation,
        contact_id: uuid.UUID,
        idle_hours: int,
    ) -> bool:
        """El gate, con **fallo → callar**.

        Asimetría deliberada con el aviso de cerrado del asistente, donde ante la duda se avisa:
        allí el silencio sería una regresión, y aquí el silencio ES el statu quo de una
        conversación `greeted`. No saber si el cliente está a mitad de un pedido y contestarle un
        folleto es el peor resultado posible; no contestar deja el mensaje donde ya estaba, en la
        bandeja, esperando a una persona.

        La ventana es la de inactividad de la conversación: la misma pregunta —"¿esto sigue
        vivo?"— contestada con el número que el dueño ya configuró.
        """
        since = datetime.now(UTC) - timedelta(hours=max(1, idle_hours))
        try:
            return await self._repo.has_live_order(
                conversation.tenant_id, contact_id, since=since
            )
        except Exception:  # noqa: BLE001 - no saber es motivo para callar, no para contestar
            logger.warning(
                "No se pudo comprobar si el contacto tiene un pedido vivo; la FAQ se calla",
                exc_info=True,
            )
            return True

    async def _render_faq(
        self, conversation: WhatsAppConversation, faq: FaqEntry
    ) -> str:
        """El texto del tenant con sus marcadores resueltos. **Nada se añade al final.**

        Ni el aviso de cerrado, ni la oferta del asistente, ni una firma: lo que el cliente recibe
        es exactamente lo que el dueño escribió. La queja que originó este trabajo fue justo una
        línea que el código pegaba y que no se podía quitar editando el texto.
        """
        tenant_id = conversation.tenant_id
        branch_id = conversation.branch_id
        identity = await self._repo.business_identity(tenant_id, branch_id)
        values = {**_identity_values(identity)}

        placeholders = find_placeholders(faq.text)
        if "menu_link" in placeholders:
            values["menu_link"] = await self.mint_store_link(conversation)
        if placeholders & {"next_opening", "hours_line"}:
            windows = [
                HoursWindow(weekday=w, open_minute=o, close_minute=c)
                for w, o, c in await self._repo.branch_hours(tenant_id, branch_id)
            ]
            # Hora LOCAL de la sede. Compararlo con UTC en Colombia (UTC-5) declaraba cerrado un
            # negocio abierto: es la piedra que ya tropezó el saludo.
            weekday, minute = weekday_and_minute()
            opening = format_next_opening(
                next_opening(windows, weekday, minute), weekday
            )
            if opening:
                values["next_opening"] = opening
            line = format_hours_line(closing_at(windows, weekday, minute), opening)
            # Sin horarios cargados no hay frase, y aquí el hueco lo lee un CLIENTE — no el dueño
            # en la pantalla de ajustes. Se omite en vez de dejar `{hours_line}` a la vista, misma
            # excepción que `{order_items}`.
            values["hours_line"] = line or ""
        return render(faq.text, values)

    # --- Enlace con token ----------------------------------------------------
    async def mint_store_link(
        self,
        conversation: WhatsAppConversation,
        settings: AutoreplySettings | None = None,
    ) -> str:
        """El enlace a la carta de la sede, con un token que precarga los datos del cliente.

        El token se renueva si está vencido y se reutiliza si sigue vivo: el cliente puede
        reabrir el enlace una hora después para pedir otra vez, y un token de un solo uso se
        leería como que el sistema está roto.
        """
        settings = settings or await self.settings_for(conversation.tenant_id)
        code = await self._repo.branch_code(
            conversation.tenant_id, conversation.branch_id
        )
        slug = await self._repo.tenant_slug(conversation.tenant_id)
        base = tenant_base_url(self._storefront_base_url, slug)
        path = f"{base}/store/{code}" if code else f"{base}/store"

        token = conversation.store_token
        expires = conversation.store_token_expires_at
        if not token or _expired(expires):
            token = secrets.token_urlsafe(_TOKEN_BYTES)
            expires = datetime.now(UTC) + timedelta(
                hours=max(1, settings.token_lifetime_hours)
            )
            await self._repo.set_store_token(
                conversation.tenant_id, conversation.id, token, expires
            )
        return f"{path}?t={token}"

    async def send_menu_link(
        self,
        conversation: WhatsAppConversation,
        contact_phone: str,
        employee_id: uuid.UUID,
    ) -> str:
        """Acción del inbox: mandar el enlace a mano. Acuña o renueva el token igual.

        Existe porque el saludo automático puede estar apagado, o porque la conversación
        ya pasó de `new` y el cliente pide la carta a mitad de charla. Sin esto, el agente
        pegaría un enlace copiado de otra sede —o sin token— y el checkout llegaría vacío.
        """
        if not self._storefront_base_url:
            raise ValidationError(
                "Falta configurar la URL pública de la carta (STOREFRONT_BASE_URL)."
            )
        link = await self.mint_store_link(conversation)
        if not await self._send_and_record(
            conversation, contact_phone, link, employee_id=employee_id
        ):
            raise ValidationError("No se pudo enviar el enlace de la carta.")
        return link

    # --- Avisos de estado del pedido -----------------------------------------
    async def notify_order_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None:
        """Cumple `CustomerNotifier`. NUNCA levanta.

        Quien llama está en mitad de una transición ya decidida —el domiciliario salió,
        la comanda se canceló—. Que el puente esté caído no puede deshacerla.
        """
        try:
            await self._notify_order_state(tenant_id, order_id, state)
        except Exception:  # noqa: BLE001 - un aviso perdido nunca cuesta la transición
            logger.warning(
                "El aviso de estado al cliente falló (pedido=%s estado=%s)",
                order_id,
                state,
                exc_info=True,
            )

    async def _notify_order_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None:
        settings = await self.settings_for(tenant_id)
        entry = _status_entry(settings, state)
        # La entrega cierra el hilo aunque el tenant haya apagado el aviso: cerrar es una
        # decisión operativa (el pedido acabó), no la consecuencia de haber hablado.
        closes = state in CLOSING_STATES
        if entry is None and not closes:
            # Transición sin mapear, o apagada. Silencio: `in_progress`, `preparing` y
            # `assigned` son ruido interno y el cliente no debe enterarse de ninguno.
            return

        context = await self._repo.order_context(tenant_id, order_id)
        if context is None or context.contact_id is None or not context.phone:
            # El pedido no lo hizo nadie que nos escribiera. No hay a quién avisar y no
            # es un error: la mayoría de los pedidos de mostrador son así.
            return
        conversation = await self._repo.find_open_conversation(
            tenant_id, context.branch_id, context.contact_id
        )
        if conversation is None:
            # Sin hilo abierto no hay dónde dejar constancia, y escribir "a pelo" a
            # alguien cuya conversación se cerró hace días es justo lo que el guard evita.
            # Es también lo que hace idempotente el cierre: el segundo rebote de `delivered`
            # ya no encuentra hilo abierto y sale por aquí.
            return

        if entry is not None:
            # La constraint manda: dos rebotes del mismo estado producen UN mensaje.
            won = await self._repo.try_claim_emission(
                tenant_id,
                context.branch_id,
                kind=EMISSION_STATUS,
                order_id=order_id,
                customer_state=state,
            )
            if won:
                text = await self._render_status(tenant_id, context, str(entry["text"]))
                await self._send_and_record(conversation, context.phone, text)

        if closes:
            # Después de enviar, nunca antes: el "fue entregado" tiene que quedar DENTRO
            # del hilo que cierra, que es lo que el agente relee mañana.
            await self._repo.close_conversation(tenant_id, conversation.id)

    # --- Comprobantes de pago -------------------------------------------------
    async def notify_payment_claim(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        status: str,
        reason: str | None,
    ) -> None:
        """Cumple `PaymentClaimNotifier`. NUNCA levanta.

        Quien llama acaba de registrar un cobro; que el puente esté caído no puede deshacerlo.
        """
        try:
            await self._notify_payment_claim(tenant_id, order_id, status, reason)
        except Exception:  # noqa: BLE001 - un aviso perdido nunca cuesta el cobro
            logger.warning(
                "El aviso del comprobante falló (pedido=%s estado=%s)",
                order_id,
                status,
                exc_info=True,
            )

    async def _notify_payment_claim(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        status: str,
        reason: str | None,
    ) -> None:
        """El texto vive aquí y no en una plantilla configurable, a propósito.

        Un "no nos sirvió tu comprobante" mal redactado por un tenant es una discusión en la
        puerta. Cuando haga falta que se pueda editar, se moverá a `AutoreplySettings` como el
        resto — hoy la prioridad es que diga exactamente lo que pasó.
        """
        text = _PAYMENT_CLAIM_TEXT.get(status)
        if text is None:
            return
        context = await self._repo.order_context(tenant_id, order_id)
        if context is None or context.contact_id is None or not context.phone:
            return
        conversation = await self._repo.find_open_conversation(
            tenant_id, context.branch_id, context.contact_id
        )
        if conversation is None:
            return
        message = text.format(order=order_number(context.order_id))
        if reason:
            message = f"{message}\n{reason}"
        if status == "accepted":
            # Con el detalle de lo comprado. "Confirmamos tu pago" a secas obliga al cliente a
            # buscar en el chat qué fue lo que pidió — y si el total subió porque él mismo
            # añadió algo, a preguntarse por qué le cobraron eso.
            message = f"{message}\n\n{await self._order_detail(tenant_id, context)}"
        await self._send_and_record(conversation, context.phone, message)

    # --- Solicitud de pago de domicilio ---------------------------------------
    async def notify_delivery_payment_request(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        request_id: uuid.UUID,
        payment_url: str,
        delivery_fee: Decimal,
    ) -> EmissionOutcome:
        """Cumple `DeliveryPaymentRequestNotifier`. NUNCA levanta; informa.

        A diferencia del resto de avisos, éste sí devuelve qué pasó: quien llama tiene en la
        mano un enlace de un solo uso que sólo existe en memoria. Si no salió, el enlace se
        pierde y alguien tiene que enterarse — de ahí `EmissionOutcome` en vez de `None`.
        """
        try:
            return await self._notify_delivery_payment_request(
                tenant_id,
                order_id,
                request_id=request_id,
                payment_url=payment_url,
                delivery_fee=delivery_fee,
            )
        except Exception:  # noqa: BLE001 - una cotización congelada no se deshace por esto
            logger.warning(
                "La solicitud de pago no se pudo emitir (pedido=%s)", order_id, exc_info=True
            )
            return EmissionOutcome(
                sent=False,
                status=EMISSION_FAILED,
                reason="Error inesperado al emitir la solicitud de pago.",
            )

    async def _notify_delivery_payment_request(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        request_id: uuid.UUID,
        payment_url: str,
        delivery_fee: Decimal,
    ) -> EmissionOutcome:
        context = await self._repo.order_context(tenant_id, order_id)
        if context is None or context.contact_id is None or not context.phone:
            # Un pedido que no hizo nadie que nos escribiera. No es un fallo: es un pedido de
            # mostrador o de teléfono, y el enlace lo tiene que pasar una persona.
            return EmissionOutcome(
                sent=False,
                status=EMISSION_NO_CONTACT,
                reason="El pedido no está vinculado a un contacto de WhatsApp.",
            )
        conversation = await self._require_thread_for_payment(tenant_id, context)
        if conversation is None:
            return EmissionOutcome(
                sent=False,
                status=EMISSION_NO_CONTACT,
                reason="El contacto no tiene ninguna conversación en esta sucursal.",
            )
        # Una emisión por solicitud, no por pedido: re-cotizar acuña otra y ésa sí sale.
        won = await self._repo.try_claim_emission(
            tenant_id,
            context.branch_id,
            kind=EMISSION_PAYMENT_REQUEST,
            order_id=order_id,
            detail=str(request_id),
        )
        if not won:
            # Otra pasada ya la mandó. Para quien llama eso es "el cliente lo tiene", que es
            # lo único que le importa — no "yo lo mandé".
            return EmissionOutcome(sent=True, status=EMISSION_SENT)

        message = await self._render_payment_request(
            tenant_id, context, payment_url=payment_url, delivery_fee=delivery_fee
        )
        if not await self._send_and_record(conversation, context.phone, message):
            return EmissionOutcome(
                sent=False,
                status=EMISSION_FAILED,
                reason="El puente de WhatsApp rechazó o no entregó el mensaje.",
            )
        return EmissionOutcome(sent=True, status=EMISSION_SENT)

    async def _require_thread_for_payment(
        self, tenant_id: uuid.UUID, context: OrderContext
    ) -> WhatsAppConversation | None:
        """El hilo donde dejar el enlace de pago, REABRIÉNDOLO si hiciera falta.

        Los avisos de estado se rinden ante un hilo cerrado, y hacen bien: un "va en camino"
        no vale reabrir una conversación que el negocio dio por terminada. Este mensaje es
        otra cosa. El cliente ACABA de hacer un pedido y está esperando el precio; negárselo
        porque cerramos el hilo cuando le entregamos el pedido ANTERIOR deja al cliente
        habitual —el bueno— sin poder pagar. `CLOSING_STATES` cierra en `delivered`, así que
        todo cliente que repite llega aquí con el hilo cerrado.

        Reabrir no viola la regla de "nunca iniciamos": esa la sostiene `is_reachable` en el
        gateway, que sigue exigiendo que este teléfono nos haya escrito. El estado del hilo es
        contabilidad nuestra para la bandeja, no el permiso de WhatsApp.
        """
        assert context.contact_id is not None  # comprobado por quien llama
        conversation = await self._repo.find_open_conversation(
            tenant_id, context.branch_id, context.contact_id
        )
        if conversation is not None:
            return conversation
        previous = await self._repo.find_latest_conversation(
            tenant_id, context.branch_id, context.contact_id
        )
        if previous is None:
            # Contacto sin ningún hilo en esta sucursal: no hay nada que reabrir y tampoco
            # sabemos que nos haya escrito AQUÍ. Eso sí es iniciar, y no se hace.
            return None
        await self._repo.update_conversation_status(
            tenant_id, previous.id, STATUS_GREETED
        )
        logger.info(
            "Hilo %s reabierto para entregar el enlace de pago del pedido %s",
            previous.id,
            context.order_id,
        )
        return previous

    async def _render_payment_request(
        self,
        tenant_id: uuid.UUID,
        context: OrderContext,
        *,
        payment_url: str,
        delivery_fee: Decimal,
    ) -> str:
        """El texto vive aquí, no en una plantilla del tenant.

        Mismo motivo que el aviso de comprobante: este mensaje pide dinero. Un total mal
        redactado no es una errata, es una discusión en la puerta. El domicilio va desglosado
        porque es la cifra nueva — el cliente ya conocía el resto cuando hizo el pedido.
        """
        return (
            f"Tu pedido {order_number(context.order_id)} ya tiene el valor del domicilio.\n\n"
            f"{await self._order_items(tenant_id, context.order_id)}\n"
            f"Domicilio: {format_money(delivery_fee)}\n"
            f"*Total a pagar: {format_money(context.total)}*\n\n"
            f"Elige cómo pagar y envíanos tu comprobante aquí:\n{payment_url}"
        )

    async def _order_items(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> str:
        """Qué compró y cuánto, una línea por producto. Sin total: ese es `{order_total}`."""
        lines = await self._repo.order_lines(tenant_id, order_id)
        return "\n".join(
            f"{line.quantity}x {line.name} · {format_money(line.line_subtotal)}"
            for line in lines
        )

    async def _order_detail(self, tenant_id: uuid.UUID, context: OrderContext) -> str:
        """Lo mismo, con el total pegado. Los asteriscos de Markdown se ven en WhatsApp."""
        detail = await self._order_items(tenant_id, context.order_id)
        total = f"Total: {format_money(context.total)}"
        return f"{detail}\n{total}" if detail else total

    async def _render_status(
        self, tenant_id: uuid.UUID, context: OrderContext, template: str
    ) -> str:
        identity = await self._repo.business_identity(tenant_id, context.branch_id)
        values = {
            **_identity_values(identity),
            "order_number": order_number(context.order_id),
            "order_total": format_money(context.total),
        }
        # El detalle se consulta sólo si el texto lo pide: los otros cinco avisos no lo
        # llevan y cobrarles una consulta a la base por un marcador ausente sobra.
        if "order_items" in find_placeholders(template):
            # Excepción a la regla de "marcador sin dato se deja a la vista": aquí el hueco
            # lo lee un cliente, no el dueño en la pantalla de ajustes. Un pedido sin
            # líneas (todo cancelado) sale con un renglón de más; con `{order_items}`
            # literal saldría con lo que parece un error del sistema.
            values["order_items"] = await self._order_items(tenant_id, context.order_id)
        return render(template, values)

    # --- Token del enlace ----------------------------------------------------
    async def resolve_store_token(self, token: str) -> ChannelContact | None:
        """Cumple `CustomerChannelDirectory`: de quién es este enlace.

        Devuelve contacto y sede, nunca un pedido. Un token vencido es indistinguible de
        uno inexistente a propósito: quien lo pruebe no aprende si alguna vez existió.
        """
        if not token:
            return None
        conversation = await self._repo.find_conversation_by_token(token)
        if conversation is None or _expired(conversation.store_token_expires_at):
            return None
        contact = await self._repo.get_contact(
            conversation.tenant_id, conversation.whatsapp_contact_id
        )
        if contact is None:
            return None
        return ChannelContact(
            tenant_id=conversation.tenant_id,
            branch_id=conversation.branch_id,
            contact_id=contact.id,
            phone=contact.phone,
            name=contact.name,
            branch_code=await self._repo.branch_code(
                conversation.tenant_id, conversation.branch_id
            ),
        )


#: Lo que se le dice al cliente sobre el comprobante que mandó. Sin plantilla configurable:
#: ver `_notify_payment_claim`.
_PAYMENT_CLAIM_TEXT = {
    "accepted": "¡Confirmamos tu pago del pedido {order}! Ya lo estamos preparando.",
    "rejected": "No pudimos confirmar el comprobante del pedido {order}.",
}


def order_number(order_id: uuid.UUID) -> str:
    """Etiqueta corta y legible de un pedido. Alias de la compartida.

    La derivación vive en `shared/domain/order_label.py` desde que se descubrió que el storefront
    se había desviado y devolvía el UUID entero: el cliente leía `C328A1B2` en su chat y
    `c328a1b2-4f5e-…` en la confirmación, para el mismo pedido.
    """
    return order_label(order_id)


def format_money(amount: Decimal) -> str:
    """`12000` → `$12.000`. Punto de miles y sin decimales, como se lee en Colombia."""
    return "$" + f"{amount:,.0f}".replace(",", ".")


def _status_entry(settings: AutoreplySettings, state: str) -> dict[str, object] | None:
    """La entrada efectiva del mapeo, o None si ese estado no habla.

    El mapeo del tenant se superpone al de fábrica clave a clave: encender `ready` no
    puede obligar a reescribir los otros cinco textos.
    """
    default = DEFAULT_STATUS_MAPPING.get(state)
    override = settings.status_mapping.get(state)
    if default is None and not isinstance(override, dict):
        return None
    merged: dict[str, object] = dict(default or {})
    if isinstance(override, dict):
        merged.update(override)
    if not merged.get("enabled") or not merged.get("text"):
        return None
    return merged


def _identity_values(identity: BusinessIdentity) -> dict[str, str]:
    """La identidad del negocio lista para interpolar.

    Un dato vacío se omite del diccionario en vez de mandarse como "": `render` deja
    entonces el marcador a la vista, que es feo pero DICE dónde está el hueco. Sustituirlo
    por vacío produciría "Llámanos al " y nadie sabría de dónde salió.
    """
    values = {
        "business_name": identity.business_name,
        "branch_name": identity.branch_name,
        "branch_address": identity.branch_address or "",
        "branch_phone": identity.branch_phone or "",
    }
    return {key: value for key, value in values.items() if value}


def _validate_faqs(faqs: list[FaqEntry]) -> None:
    """Todo lo que puede estar mal en una FAQ, dicho AL GUARDAR y nombrando al culpable.

    Misma postura que los marcadores del saludo: descubrir a las 8pm que una FAQ no dispara, con
    un cliente esperando, no le sirve a nadie. Aquí el dueño está mirando la pantalla.
    """
    seen: set[str] = set()
    for index, faq in enumerate(faqs, start=1):
        where = f'FAQ "{faq.name}"' if faq.name.strip() else f"FAQ #{index}"
        if not faq.id.strip():
            raise ValidationError(f"{where}: falta el identificador.")
        if faq.id in seen:
            raise ValidationError(f"{where}: identificador repetido ({faq.id}).")
        seen.add(faq.id)
        if not faq.name.strip():
            raise ValidationError(f"{where}: ponle un nombre para reconocerla.")
        triggers = [t for t in faq.triggers if t.strip()]
        if not triggers:
            raise ValidationError(
                f"{where}: necesita al menos una palabra o frase que la dispare."
            )
        if not faq.text.strip():
            raise ValidationError(f"{where}: necesita un texto para contestar.")
        _reject_unknown(faq.text, FAQ_PLACEHOLDERS, where)
        for trigger in triggers:
            reserved = reserved_words_in(trigger)
            if reserved:
                # Por CONTENCIÓN, no por igualdad: `cancelaciones` no es `cancelar`, pasaría una
                # comprobación por igualdad y luego no dispararía nunca —porque el mensaje que la
                # activaría se va a una persona antes—. Una FAQ encendida que no puede coincidir
                # es peor que una rechazada: nada la explica. Así que el error enseña.
                offenders = ", ".join(f"«{word}»" for word in reserved)
                raise ValidationError(
                    f"{where}: el gatillo «{trigger}» contiene {offenders}, que el canal "
                    "reserva — esos mensajes los atiende una persona, así que la FAQ nunca "
                    "llegaría a contestar. Usa otras palabras."
                )


def _reject_unknown(text: str, allowed: frozenset[str], where: str) -> None:
    """422 nombrando al culpable. "Marcador inválido" a secas no arregla nada."""
    unknown = unknown_placeholders(text, allowed)
    if unknown:
        offenders = ", ".join(f"{{{name}}}" for name in sorted(unknown))
        raise ValidationError(
            f"Marcadores no válidos en {where}: {offenders}. "
            f"Disponibles: {', '.join('{' + p + '}' for p in sorted(allowed))}."
        )


def _expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    # SQLite devuelve datetimes naive; comparar en UTC o la resta explota.
    moment = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    return moment <= datetime.now(UTC)
