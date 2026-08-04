"""El flujo: quién habla con el asistente, con qué historia y cuándo deja de hacerlo.

Dos vías entran por aquí y las dos salen por el MISMO punto de estrangulamiento
(`MeteredAssistant.ask`), que es lo que hace que medir sea cierto y no una intención:

- **WhatsApp.** Una conversación saludada (`greeted`) sólo pasa a `bot` si el cliente lo
  pide. Entrar al asistente es una decisión suya: quien escribe "hola" quiere una persona
  hasta que diga lo contrario, y meterlo en un bot por defecto es cómo se pierde un cliente.
- **Administración.** Un empleado autenticado pregunta con SU registro y SU sucursal.

Tres cosas que no son detalles:

- **Pedir un humano gana siempre.** Se comprueba ANTES de llamar al modelo: cuesta cero y
  evita la respuesta más cara posible, que es la que llega cuando alguien ya se hartó.
- **La historia es una ventana fija.** Es el principal motor del coste de entrada, así que
  se recortan turnos, no se manda la conversación entera.
- **El prompt no sostiene ninguna frontera.** Lo que el asistente puede saber lo decide el
  registro de herramientas; el texto de aquí sólo decide cómo lo dice.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from restaurante.modules.assistant.application.use_cases.metering import (
    AssistantAnswer,
    CallerContext,
    MeteredAssistant,
)
from restaurante.modules.assistant.domain.entities import (
    CALLER_CUSTOMER,
    CALLER_EMPLOYEE,
    AssistantConversationState,
    ConversationTurn,
)
from restaurante.modules.assistant.domain.errors import (
    AssistantProviderError,
    QuotaExhaustedError,
    RateLimitedError,
)
from restaurante.modules.assistant.domain.ports import (
    AssistantRepository,
    ConversationChannel,
    OpeningHoursReader,
    ToolSpec,
)

logger = logging.getLogger(__name__)

#: Estados de la conversación de WhatsApp que le importan al asistente. Los dos primeros ya
#: existían (`whatsapp-autoreply`); los dos últimos los añade este cambio.
STATUS_GREETED = "greeted"
STATUS_BOT = "bot"
STATUS_HUMAN = "human"

#: Cómo se entra. El saludo ofrece "escribe 1", así que "1" tiene que funcionar; y quien
#: escribe "asistente" está pidiendo lo mismo con otras palabras.
OPT_IN_WORDS = {"1", "asistente", "bot"}

#: Cómo se sale. Se mira antes de gastar un token: quien pide una persona ya decidió que el
#: bot no le sirve, y contestarle con el bot es la forma más cara de perder a alguien.
HANDOFF_WORDS = (
    "humano",
    "persona",
    "asesor",
    "agente",
    "alguien",
    "operador",
)

#: Lo que el asistente NO puede resolver ni mandando a ninguna pantalla: cancelar un pedido y
#: devolver plata. Se miran antes del modelo porque no hace falta leer para saberlo.
#:
#: "Quitar" NO está aquí a propósito, y es la decisión fina de este bloque: "quítame la cebolla"
#: es una exclusión que la vista SÍ hace, y "quítame la gaseosa" es una línea que no. Distinguir
#: las dos exige entender la frase, que es justo lo que el modelo hace bien y una lista de
#: palabras hace mal — y equivocarse mandaría a una persona a alguien que sólo quería tocar una
#: casilla.
REFUND_WORDS = (
    "cancelar",
    "cancela",
    "anular",
    "anula",
    "devolver",
    "devolución",
    "devolucion",
    "reembolso",
)

CONFIRM_BOT = (
    "Listo, te atiendo yo. Pregúntame por la carta, los horarios o tu pedido. "
    "Escribe *humano* cuando quieras hablar con alguien del equipo."
)
CONFIRM_HANDOFF = "Claro, ahora te atiende una persona del equipo."

#: Cancelar y devolver los hace una persona. Se avisa Y se pasa la conversación, porque decir
#: "lo hace una persona" sin ponerla delante deja al cliente esperando a nadie.
CONFIRM_NEEDS_PERSON = (
    "Eso lo tiene que ver una persona del equipo, no yo. Ya les aviso y te escriben."
)

#: Fuera de horario. Es una CADENA, no un prompt: no hay nadie detrás, y pagarle al modelo por
#: decir "estamos cerrados" es la llamada más fácil de no hacer.
#:
#: Las dos variantes comparten el arranque a propósito: es lo que permite reconocer el aviso en
#: el hilo y no repetirlo (`_already_said_closed`) sin guardar un estado aparte.
CLOSED_PREFIX = "Ahora mismo estamos cerrados."
CLOSED_MESSAGE = CLOSED_PREFIX + " Abrimos {when} y te respondemos."
CLOSED_MESSAGE_NO_HOURS = CLOSED_PREFIX + " Te respondemos en cuanto abramos."

_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

#: Lo que se contesta cuando se acabó el saldo y el tenant no configuró su propio texto.
#:
#: Es una CADENA, no un prompt. Explicarle al cliente que se agotó la cuota pidiéndoselo al
#: modelo cuesta exactamente la llamada que no hay con qué pagar — y es la llamada que se
#: haría justo cuando el tenant ya se pasó de lo que compró.
DEFAULT_FALLBACK = (
    "Ahora mismo no puedo responderte yo, pero puedes ver la carta y pedir aquí:\n{link}\n"
    "También puede atenderte una persona del equipo."
)

#: El prompt. Fija el TONO y el formato, nunca los permisos.
#:
#: La regla del texto plano no es estética: WhatsApp usa un asterisco simple para negrita, así
#: que un modelo escribiendo Markdown manda `**22:00**` y el cliente ve los asteriscos. Es el
#: detalle que delata a un bot, y salió en la primera llamada real.
CUSTOMER_PROMPT = """Eres quien atiende el WhatsApp de {business}. Hablas en español, de tú, \
con frases cortas y cálidas.

Reglas:
- Responde SÓLO con lo que devuelvan tus herramientas. Si no tienes el dato, dilo y ofrece \
pasar con una persona. No inventes precios, platos ni horarios.
- Escribe en texto plano. Nada de Markdown, ni asteriscos dobles, ni listas numeradas largas.
- Si quiere pedir, dale este enlace: {store_link}
- Si quiere AÑADIR algo a un pedido que ya hizo, ponerle una adición, quitarle un ingrediente \
o cambiar un plato por otro, usa la herramienta del enlace de su pedido y dáselo. Ahí lo hace \
él mismo.
- Si quiere QUITAR un plato del pedido, bajar la cantidad, cancelar o que le devuelvan la \
plata, NO le des ese enlace: esa pantalla no lo hace. Dile que lo ve una persona del equipo.
- No puedes tomar pedidos, cambiar precios ni cancelar nada. Para eso, el enlace o una persona.
- Si pide hablar con alguien, dile que ya avisas al equipo."""

EMPLOYEE_PROMPT = """Eres el asistente interno de {business}, hablando con alguien del \
equipo sobre la sede en la que trabaja. Español, directo, sin rodeos.

Reglas:
- Responde SÓLO con lo que devuelvan tus herramientas, y di de qué periodo son los números.
- Si te falta una herramienta para contestar, dilo claramente: puede ser que esa persona no \
tenga ese permiso.
- No puedes modificar nada: sólo consultar."""


@dataclass
class InboundContext:
    """El mensaje que acaba de llegar por WhatsApp, con lo que hace falta para contestarlo."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    conversation_id: uuid.UUID
    contact_id: uuid.UUID
    contact_phone: str
    status: str
    text: str


class AssistantConversationService:
    def __init__(
        self,
        metered: MeteredAssistant,
        repo: AssistantRepository,
        channel: ConversationChannel,
        *,
        business_name: str = "el restaurante",
        history_turns: int = 6,
        hours: OpeningHoursReader | None = None,
    ) -> None:
        self._metered = metered
        self._repo = repo
        self._channel = channel
        self._business = business_name
        self._history_turns = history_turns
        # Sin lector de horario el asistente contesta a cualquier hora, que es como se
        # comportaba antes de este cambio. Estar cerrado apaga al ASISTENTE ENTERO: ni entra
        # nadie en modo bot ni se llama al modelo. No apaga la vista de "mi pedido" —corregir
        # a las once de la noche un pedido que nadie ha empezado no molesta a nadie—, pero
        # contestar por chat cuando no hay nadie detrás sí promete algo que no hay.
        self._hours = hours

    # --- Vía WhatsApp -------------------------------------------------------
    async def handle_inbound(
        self, inbound: InboundContext, tools: list[ToolSpec]
    ) -> bool:
        """Contesta si a esta conversación le toca el asistente. `False` si no era suya.

        Devolver `False` es el caso normal y sano: la mayoría de las conversaciones las
        atiende una persona, y este método no debe tocarlas.
        """
        text = inbound.text.strip()
        if not text:
            return False

        if inbound.status == STATUS_GREETED and _is_opt_in(text):
            if not await self._entitled(inbound.tenant_id):
                # El saludo ofreció el asistente y este negocio no lo tiene (o lo apagó).
                # Meterlo en modo bot igualmente lo dejaría escribiendo a un sitio que no
                # contesta: silencio con pinta de avería. Se queda como está y lo atiende
                # una persona, que es lo que habría pasado sin la oferta.
                logger.info(
                    "Un cliente aceptó el asistente en un tenant sin derecho (%s)",
                    inbound.tenant_id,
                )
                return False
            if not await self._is_open(inbound):
                # Cerrado: no se entra al asistente. Fuera de horario no contesta —lo apaga
                # `_open_now`—, así que cambiar la conversación a modo bot sería cambiarle de
                # dueño para que siga sin contestarle nadie, y además la sacaría de la cola
                # de lo que una persona atiende mañana.
                #
                # Se queda en `greeted` y NO se contesta nada: el saludo de cerrado ya dijo a
                # qué hora abrimos, y repetirlo aquí es el bot diciendo dos veces lo mismo.
                # El "1" sigue funcionando cuando el negocio abra.
                logger.info(
                    "Un cliente aceptó el asistente con el negocio cerrado (sede %s)",
                    inbound.branch_id,
                )
                return False
            await self._channel.set_status(
                inbound.tenant_id, inbound.conversation_id, STATUS_BOT
            )
            await self._channel.send(
                inbound.tenant_id,
                inbound.branch_id,
                inbound.conversation_id,
                inbound.contact_phone,
                CONFIRM_BOT,
            )
            return True

        if inbound.status != STATUS_BOT:
            return False

        if _wants_human(text):
            # Sin llamar al modelo. Quien pide una persona ya no quiere otra respuesta
            # automática, por buena que sea.
            await self._channel.set_status(
                inbound.tenant_id, inbound.conversation_id, STATUS_HUMAN
            )
            await self._channel.send(
                inbound.tenant_id,
                inbound.branch_id,
                inbound.conversation_id,
                inbound.contact_phone,
                CONFIRM_HANDOFF,
            )
            return True

        if _needs_a_person(text):
            # Cancelar y devolver no los hace ni el asistente ni la vista de "mi pedido". Se
            # comprueba antes del modelo por lo mismo que pedir un humano: la respuesta ya se
            # sabe, y pagarla sería pagar por no ayudar.
            await self._channel.set_status(
                inbound.tenant_id, inbound.conversation_id, STATUS_HUMAN
            )
            await self._channel.send(
                inbound.tenant_id,
                inbound.branch_id,
                inbound.conversation_id,
                inbound.contact_phone,
                CONFIRM_NEEDS_PERSON,
            )
            return True

        if not await self._open_now(inbound):
            # Cerrado: una frase fija con la próxima apertura y ni una llamada. La
            # conversación se queda en `bot`, así que cuando el negocio abra y el cliente
            # vuelva a escribir, el asistente sigue siendo suyo.
            return True

        ref = f"whatsapp:{inbound.conversation_id}"
        state = await self._repo.get_state(inbound.tenant_id, ref) or (
            AssistantConversationState(
                tenant_id=inbound.tenant_id,
                conversation_ref=ref,
                caller_kind=CALLER_CUSTOMER,
                branch_id=inbound.branch_id,
            )
        )
        link = await self._channel.store_link(
            inbound.tenant_id, inbound.conversation_id
        )
        try:
            answer = await self._metered.ask(
                CallerContext(
                    tenant_id=inbound.tenant_id,
                    caller_kind=CALLER_CUSTOMER,
                    conversation_ref=ref,
                    branch_id=inbound.branch_id,
                ),
                text,
                system_prompt=CUSTOMER_PROMPT.format(
                    business=self._business, store_link=link
                ),
                tools=tools,
                turns=state.turns,
            )
        except QuotaExhaustedError:
            # Se degrada, no falla. Y la conversación se queda en `bot` a propósito: sigue
            # apareciendo en el inbox y cualquiera puede tomarla, que es lo que convierte
            # "se acabó el saldo" en "te atiende una persona" en vez de en silencio.
            await self._send_fallback(inbound, link)
            return True
        except (RateLimitedError, AssistantProviderError):
            # Ni una palabra. Un cliente escribiendo diez veces seguidas recibiría diez
            # disculpas automáticas, que es cómo se marca un número como spam; el mensaje
            # queda en el inbox y lo ve una persona.
            logger.warning(
                "El asistente no contestó a la conversación %s",
                inbound.conversation_id,
                exc_info=True,
            )
            return False
        await self._remember(state, text, answer.text)
        await self._channel.send(
            inbound.tenant_id,
            inbound.branch_id,
            inbound.conversation_id,
            inbound.contact_phone,
            answer.text,
        )
        return True

    # --- Vía administración -------------------------------------------------
    async def ask_as_employee(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        tools: list[ToolSpec],
    ) -> AssistantAnswer:
        """El chat del panel. Mismo punto de estrangulamiento, otro registro.

        El hilo se guarda por usuario Y sucursal: "¿cuánto vendimos ayer?" no significa lo
        mismo en dos sedes, así que cambiar de sede empieza una conversación distinta en vez
        de arrastrar contexto de la anterior.
        """
        ref = f"admin:{user_id}:{branch_id}"
        state = await self._repo.get_state(tenant_id, ref) or (
            AssistantConversationState(
                tenant_id=tenant_id,
                conversation_ref=ref,
                caller_kind=CALLER_EMPLOYEE,
                branch_id=branch_id,
            )
        )
        answer = await self._metered.ask(
            CallerContext(
                tenant_id=tenant_id,
                caller_kind=CALLER_EMPLOYEE,
                conversation_ref=ref,
                branch_id=branch_id,
            ),
            question,
            system_prompt=EMPLOYEE_PROMPT.format(business=self._business),
            tools=tools,
            turns=state.turns,
        )
        await self._remember(state, question, answer.text)
        return answer

    # --- Interno ------------------------------------------------------------
    async def _entitled(self, tenant_id: uuid.UUID) -> bool:
        """¿Este negocio tiene el asistente comprado y encendido?

        Se pregunta ANTES de cambiar el estado, no al contestar: el punto de estrangulamiento
        también lo comprueba —y es él quien manda—, pero para entonces la conversación ya
        estaría en modo bot esperando una respuesta que no va a llegar.
        """
        entitlement = await self._repo.get_entitlement(tenant_id)
        return entitlement is not None and entitlement.is_enabled

    async def _hours_now(
        self, inbound: InboundContext
    ) -> tuple[bool, tuple[int, int] | None]:
        """`(abierto, próxima apertura)`. **Nunca levanta y nunca escribe nada.**

        Un fallo leyendo el horario cuenta como ABIERTO: la respuesta cara es la que no llega,
        y quedarse mudo por no saber si estamos abiertos es peor que contestar de más. Sin
        lector enchufado, igual — es como se comportaba antes de que el horario le importara.
        """
        if self._hours is None:
            return True, None
        try:
            return await self._hours.status(inbound.tenant_id, inbound.branch_id)
        except Exception:  # noqa: BLE001 - no saber el horario no puede costar la respuesta
            logger.warning("No se pudo leer el horario de la sede", exc_info=True)
            return True, None

    async def _is_open(self, inbound: InboundContext) -> bool:
        """¿Hay alguien detrás ahora mismo? Sin decirle nada al cliente.

        Es la mitad silenciosa de `_open_now`, y existe para el momento de entrar al
        asistente: ahí lo que hace falta es NO abrir la puerta, no anunciar el horario.
        """
        open_now, _next_opening = await self._hours_now(inbound)
        return open_now

    async def _open_now(self, inbound: InboundContext) -> bool:
        """`True` si hay alguien detrás. Si no, contesta el horario UNA VEZ y devuelve `False`.

        Una vez por tanda de cerrado, no por mensaje: quien escribe "hola", "¿hay alguien?" y
        "1" a las once de la noche recibiría tres veces la misma frase, que es cómo se marca un
        número como spam y cómo se le enseña a un cliente a silenciar el chat. Al abrir, el
        primer aviso siguiente vuelve a salir: entre medias contestó el modelo o una persona.
        """
        open_now, next_opening = await self._hours_now(inbound)
        if open_now:
            return True
        if not await self._already_said_closed(inbound):
            await self._channel.send(
                inbound.tenant_id,
                inbound.branch_id,
                inbound.conversation_id,
                inbound.contact_phone,
                _closed_text(next_opening),
            )
        return False

    async def _already_said_closed(self, inbound: InboundContext) -> bool:
        """¿Lo último que salió por este hilo fue ya el aviso de cerrado?

        Se mira el HILO y no un contador propio: es la única fuente que sobrevive a un reinicio
        y que no se desincroniza cuando quien contestó fue otro proceso. Si en medio contestó
        una persona desde la bandeja, lo último no es el aviso y el aviso vuelve a salir — que
        es lo correcto: la conversación se movió.

        Ante un fallo leyendo, se avisa. Repetir una frase es molesto; callar la primera vez
        deja al cliente esperando a nadie.
        """
        try:
            last = await self._channel.last_outbound_text(
                inbound.tenant_id, inbound.conversation_id
            )
        except Exception:  # noqa: BLE001 - no poder leer el hilo no puede callar el aviso
            logger.warning("No se pudo leer lo último dicho en el hilo", exc_info=True)
            return False
        return bool(last and last.startswith(CLOSED_PREFIX))

    async def _send_fallback(self, inbound: InboundContext, link: str) -> None:
        """El texto del tenant, o el de fábrica. **Cero llamadas al modelo.**"""
        entitlement = await self._repo.get_entitlement(inbound.tenant_id)
        template = (
            entitlement.fallback_message
            if entitlement and entitlement.fallback_message
            else DEFAULT_FALLBACK
        )
        await self._channel.send(
            inbound.tenant_id,
            inbound.branch_id,
            inbound.conversation_id,
            inbound.contact_phone,
            template.replace("{link}", link),
        )

    async def _remember(
        self, state: AssistantConversationState, question: str, answer: str
    ) -> None:
        """Guarda el turno ya recortado a la ventana.

        Se recorta al GUARDAR y no al enviar: lo que no cabe no se guarda, en vez de
        guardarse para descartarlo en la siguiente pregunta.
        """
        state.turns = (
            state.turns
            + [ConversationTurn("user", question), ConversationTurn("assistant", answer)]
        )[-self._history_turns :]
        await self._repo.save_state(state)


def _is_opt_in(text: str) -> bool:
    return text.strip().lower().strip(".!¡") in OPT_IN_WORDS


def _wants_human(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in HANDOFF_WORDS)


def _needs_a_person(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in REFUND_WORDS)


def _closed_text(next_opening: tuple[int, int] | None) -> str:
    """La frase de cerrado. Con la próxima apertura si se sabe; sin inventarla si no.

    "Abrimos mañana" cuando mañana es domingo y no se abre es peor que no decir cuándo: el
    cliente vuelve, no hay nadie, y la próxima vez ya no escribe.
    """
    if next_opening is None:
        return CLOSED_MESSAGE_NO_HOURS
    weekday, minute = next_opening
    when = f"el {_DAYS[weekday % 7]} a las {minute // 60:02d}:{minute % 60:02d}"
    return CLOSED_MESSAGE.format(when=when)
