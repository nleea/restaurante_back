"""El asistente ENRUTA hacia «mi pedido»; no escribe en el pedido.

Tres cosas se prueban aquí, y las tres son sobre cuándo NO se llama al modelo o qué NO se
manda:

- Cancelar y devolver van a una persona, sin gastar una llamada y sin enseñar el enlace: esa
  pantalla no lo hace, y mandarla es una respuesta equivocada, no una a medias.
- Cerrado no cuesta ni un token: una frase fija con la próxima apertura.
- La herramienta del enlace sólo LEE. Devuelve el enlace del pedido abierto de ESA persona, y
  nada cuando no hay ninguno.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import pytest

from restaurante.modules.assistant.application.use_cases.conversation import (
    STATUS_BOT,
    STATUS_HUMAN,
    AssistantConversationService,
    InboundContext,
)
from restaurante.modules.assistant.application.use_cases.metering import AssistantAnswer
from restaurante.modules.assistant.application.use_cases.tools import (
    build_customer_registry,
)
from restaurante.modules.assistant.domain.entities import (
    AssistantConversationState,
    AssistantEntitlement,
)
from restaurante.shared.links import order_edit_url

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()
CONVERSATION = uuid.uuid4()
CONTACT = uuid.uuid4()


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.statuses: list[str] = []

    async def send(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool:
        self.sent.append(text)
        return True

    async def set_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None:
        self.statuses.append(status)

    async def store_link(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str:
        return "https://demo.test/store/centro?t=abc"

    async def last_outbound_text(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        return self.sent[-1] if self.sent else None


class FakeMetered:
    def __init__(self) -> None:
        self.calls = 0

    async def ask(self, caller: Any, question: str, **kwargs: Any) -> AssistantAnswer:
        self.calls += 1
        return AssistantAnswer(
            text="lo que sea",
            model="fake",
            tokens_in=1,
            tokens_out=1,
            provider_cost=Decimal("0"),
            billed_units=1,
        )


class FakeRepo:
    def __init__(self) -> None:
        self.states: dict[str, AssistantConversationState] = {}

    async def get_entitlement(self, tenant_id: uuid.UUID) -> Any:
        return AssistantEntitlement(tenant_id=tenant_id, is_enabled=True)

    async def get_state(
        self, tenant_id: uuid.UUID, ref: str
    ) -> AssistantConversationState | None:
        return self.states.get(ref)

    async def save_state(
        self, state: AssistantConversationState
    ) -> AssistantConversationState:
        self.states[state.conversation_ref] = state
        return state


class FakeHours:
    def __init__(
        self, open_now: bool, next_opening: tuple[int, int] | None = None
    ) -> None:
        self._open = open_now
        self._next = next_opening

    async def status(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> tuple[bool, tuple[int, int] | None]:
        return self._open, self._next


def _service(
    metered: FakeMetered, channel: FakeChannel, hours: FakeHours | None = None
) -> AssistantConversationService:
    return AssistantConversationService(
        cast(Any, metered),
        cast(Any, FakeRepo()),
        cast(Any, channel),
        business_name="La Prueba",
        hours=cast(Any, hours),
    )


def _inbound(text: str) -> InboundContext:
    return InboundContext(
        tenant_id=TENANT,
        branch_id=BRANCH,
        conversation_id=CONVERSATION,
        contact_id=CONTACT,
        contact_phone="573001112233",
        status=STATUS_BOT,
        text=text,
    )


# --- Enrutar, no escribir ----------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "quiero cancelar mi pedido",
        "cancela lo que pedí",
        "¿me pueden hacer una devolución?",
        "quiero el reembolso",
    ],
)
async def test_cancelling_or_refunding_goes_to_a_person_without_a_model_call(
    text: str,
) -> None:
    metered, channel = FakeMetered(), FakeChannel()
    assert await _service(metered, channel).handle_inbound(_inbound(text), [])
    assert metered.calls == 0, "la respuesta ya se sabía; pagarla es pagar por no ayudar"
    assert channel.statuses == [STATUS_HUMAN]
    # Y sobre todo: NO se manda el enlace. Esa pantalla no cancela, así que mandarla sería
    # llevar al cliente a un sitio que no hace lo que pidió.
    assert not any("my-order" in message for message in channel.sent)


@pytest.mark.asyncio
async def test_asking_to_remove_an_ingredient_still_reaches_the_model() -> None:
    """"Quítame la cebolla" es una exclusión, y la vista SÍ la hace.

    Es la razón por la que "quitar" no está en la lista de palabras: distinguirla de "quítame
    la gaseosa" exige entender la frase. Mandar a una persona a quien sólo quería tocar una
    casilla es el error que esta prueba fija.
    """
    metered, channel = FakeMetered(), FakeChannel()
    assert await _service(metered, channel).handle_inbound(
        _inbound("quítame la cebolla del ceviche"), []
    )
    assert metered.calls == 1
    assert channel.statuses == []


# --- Cerrado -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_closed_answers_with_the_next_opening_and_no_model_call() -> None:
    metered, channel = FakeMetered(), FakeChannel()
    hours = FakeHours(open_now=False, next_opening=(1, 11 * 60 + 30))
    assert await _service(metered, channel, hours).handle_inbound(
        _inbound("¿tienen ceviche?"), []
    )
    assert metered.calls == 0, "no hay nadie detrás: eso no se le pregunta al modelo"
    assert channel.sent == [
        "Ahora mismo estamos cerrados. Abrimos el martes a las 11:30 y te respondemos."
    ]
    # La conversación sigue siendo del asistente: cuando abran y vuelva a escribir, contesta.
    assert channel.statuses == []


@pytest.mark.asyncio
async def test_closed_without_configured_hours_says_so_without_inventing_a_day() -> None:
    metered, channel = FakeMetered(), FakeChannel()
    assert await _service(metered, channel, FakeHours(open_now=False)).handle_inbound(
        _inbound("¿tienen ceviche?"), []
    )
    assert metered.calls == 0
    assert channel.sent == [
        "Ahora mismo estamos cerrados. Te respondemos en cuanto abramos."
    ]


@pytest.mark.asyncio
async def test_the_closed_notice_goes_out_once_not_per_message() -> None:
    """Tres mensajes de noche, un aviso.

    Repetir la misma frase en cada mensaje es cómo se marca un número como spam — y cómo se le
    enseña a un cliente a silenciar el chat. Al abrir vuelve a valer: entre medias habrá
    contestado el modelo o una persona, así que lo último del hilo ya no es el aviso.
    """
    metered, channel = FakeMetered(), FakeChannel()
    service = _service(metered, channel, FakeHours(open_now=False, next_opening=(1, 8 * 60)))

    # Nada de "¿hay alguien?": "alguien" pide una persona y sale por el otro camino, antes
    # del horario. Estos tres son preguntas normales de un cliente de noche.
    for text in ("hola", "¿están abiertos?", "¿tienen ceviche?"):
        assert await service.handle_inbound(_inbound(text), [])

    assert channel.sent == [
        "Ahora mismo estamos cerrados. Abrimos el martes a las 08:00 y te respondemos."
    ]
    assert metered.calls == 0


@pytest.mark.asyncio
async def test_a_person_replying_in_between_lets_the_notice_out_again() -> None:
    """Si en medio contestó alguien, lo último del hilo ya no es el aviso: vuelve a salir."""
    metered, channel = FakeMetered(), FakeChannel()
    service = _service(metered, channel, FakeHours(open_now=False))

    assert await service.handle_inbound(_inbound("hola"), [])
    channel.sent.append("Buenas, mañana te ayudo.")  # una persona, desde la bandeja
    assert await service.handle_inbound(_inbound("¿y el domicilio?"), [])

    notice = "Ahora mismo estamos cerrados. Te respondemos en cuanto abramos."
    assert channel.sent.count(notice) == 2


@pytest.mark.asyncio
async def test_a_thread_that_cannot_be_read_still_gets_the_notice() -> None:
    """Ante la duda se avisa: repetir molesta, callar deja al cliente esperando a nadie."""

    class BlindChannel(FakeChannel):
        async def last_outbound_text(
            self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
        ) -> str | None:
            raise RuntimeError("sin hilo")

    metered, channel = FakeMetered(), BlindChannel()
    service = _service(metered, channel, FakeHours(open_now=False))

    assert await service.handle_inbound(_inbound("hola"), [])
    assert await service.handle_inbound(_inbound("¿están abiertos?"), [])
    assert len(channel.sent) == 2


@pytest.mark.asyncio
async def test_open_answers_normally() -> None:
    metered, channel = FakeMetered(), FakeChannel()
    hours = FakeHours(open_now=True)
    assert await _service(metered, channel, hours).handle_inbound(
        _inbound("¿tienen ceviche?"), []
    )
    assert metered.calls == 1


@pytest.mark.asyncio
async def test_a_broken_clock_does_not_silence_the_assistant() -> None:
    """No saber si estamos abiertos no puede costar la respuesta: la cara es la que no llega."""

    class ExplodingHours:
        async def status(
            self, tenant_id: uuid.UUID, branch_id: uuid.UUID
        ) -> tuple[bool, tuple[int, int] | None]:
            raise RuntimeError("sin horario")

    metered, channel = FakeMetered(), FakeChannel()
    service = AssistantConversationService(
        cast(Any, metered),
        cast(Any, FakeRepo()),
        cast(Any, channel),
        hours=cast(Any, ExplodingHours()),
    )
    assert await service.handle_inbound(_inbound("¿tienen ceviche?"), [])
    assert metered.calls == 1


# --- La herramienta del enlace ----------------------------------------------
@dataclass
class _Order:
    id: uuid.UUID
    edit_token: str | None


class FakeOrders:
    """Sólo `list_orders`. Cualquier otra cosa que se le pida es una escritura que no toca."""

    def __init__(self, orders: list[_Order]) -> None:
        self._orders = orders
        self.filters: dict[str, Any] = {}

    async def list_orders(self, tenant_id: uuid.UUID, **kwargs: Any) -> list[_Order]:
        self.filters = kwargs
        return self._orders

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - defensa
        raise AssertionError(f"la herramienta del enlace no debería llamar a {name}")


def _link_registry(orders: FakeOrders) -> list[Any]:
    stub = cast(Any, object())
    return build_customer_registry(
        tenant_id=TENANT,
        branch_id=BRANCH,
        storefront=stub,
        business=stub,
        orders=cast(Any, orders),
        whatsapp_contact_id=CONTACT,
        order_edit_link=lambda token: order_edit_url("https://test.local", "demo", token),
    )


def _tool(tools: list[Any], name: str) -> Any:
    return next(tool for tool in tools if tool.name == name)


@pytest.mark.asyncio
async def test_the_link_tool_hands_this_contact_its_own_open_order() -> None:
    orders = FakeOrders([_Order(uuid.uuid4(), "tok-abc")])
    answer = await _tool(_link_registry(orders), "my_order_link").run({})

    assert "https://demo.test.local/my-order/tok-abc" in answer
    # Filtrado por ESTE contacto y por pedidos abiertos: el modelo no elige de quién es.
    assert orders.filters == {"status": "open", "whatsapp_contact_id": CONTACT}


@pytest.mark.asyncio
async def test_the_link_tool_says_there_is_nothing_when_there_is_no_open_order() -> None:
    answer = await _tool(_link_registry(FakeOrders([])), "my_order_link").run({})
    assert "no tiene ningún pedido abierto" in answer.lower()
    assert "my-order" not in answer


@pytest.mark.asyncio
async def test_an_order_without_a_token_is_not_offered() -> None:
    """Los pedidos anteriores a este cambio no tienen token, y media URL es peor que ninguna."""
    orders = FakeOrders([_Order(uuid.uuid4(), None)])
    answer = await _tool(_link_registry(orders), "my_order_link").run({})
    assert "my-order" not in answer


def test_without_a_link_builder_the_tool_does_not_exist() -> None:
    """Sin dominio público configurado no hay herramienta, no una que devuelva basura."""
    stub = cast(Any, object())
    tools = build_customer_registry(
        tenant_id=TENANT,
        branch_id=BRANCH,
        storefront=stub,
        business=stub,
        orders=stub,
        whatsapp_contact_id=CONTACT,
    )
    assert "my_order_link" not in {tool.name for tool in tools}


def test_the_link_tool_never_reaches_an_anonymous_contact() -> None:
    """Sin saber quién escribe no hay enlace: sería el pedido de cualquiera."""
    stub = cast(Any, object())
    tools = build_customer_registry(
        tenant_id=TENANT,
        branch_id=BRANCH,
        storefront=stub,
        business=stub,
        orders=stub,
        order_edit_link=lambda token: f"https://test.local/my-order/{token}",
    )
    assert "my_order_link" not in {tool.name for tool in tools}
