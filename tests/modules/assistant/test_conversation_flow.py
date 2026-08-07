"""El flujo de WhatsApp: quién entra al asistente, quién sale y qué cuesta cada cosa.

Lo que más se prueba aquí no es que conteste, sino **cuándo NO llama al modelo**: aceptar el
asistente y pedir una persona son los dos momentos en que gastar un token sería tirar dinero,
y son justo los que un refactor descuidado convierte en una llamada más.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest

from restaurante.modules.assistant.application.use_cases.conversation import (
    STATUS_BOT,
    STATUS_GREETED,
    STATUS_HUMAN,
    AssistantConversationService,
    InboundContext,
)
from restaurante.modules.assistant.application.use_cases.metering import AssistantAnswer
from restaurante.modules.assistant.domain.entities import (
    AssistantConversationState,
    AssistantEntitlement,
)

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
        """Lo último que salió. En el hilo real es lo mismo, leído de la base."""
        return self.sent[-1] if self.sent else None


class FakeMetered:
    """Cuenta las llamadas. Es la afirmación central de media suite."""

    def __init__(self, answer: str = "Abrimos a las 11.") -> None:
        self.calls = 0
        self.last_turns: list[Any] = []
        self._answer = answer

    async def ask(
        self, caller: Any, question: str, **kwargs: Any
    ) -> AssistantAnswer:
        self.calls += 1
        self.last_turns = list(kwargs.get("turns") or [])
        return AssistantAnswer(
            text=self._answer,
            model="fake",
            tokens_in=10,
            tokens_out=5,
            provider_cost=Decimal("0"),
            billed_units=1,
        )


class FakeRepo:
    def __init__(self, entitled: bool = True) -> None:
        self.states: dict[str, AssistantConversationState] = {}
        self._entitled = entitled

    async def get_entitlement(self, tenant_id: uuid.UUID) -> Any:
        if not self._entitled:
            return None
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
    metered: FakeMetered,
    channel: FakeChannel,
    repo: FakeRepo,
    history: int = 4,
    hours: FakeHours | None = None,
) -> AssistantConversationService:
    return AssistantConversationService(
        cast(Any, metered),
        cast(Any, repo),
        cast(Any, channel),
        business_name="La Prueba",
        history_turns=history,
        hours=cast(Any, hours),
    )


def _inbound(status: str, text: str) -> InboundContext:
    return InboundContext(
        tenant_id=TENANT,
        branch_id=BRANCH,
        conversation_id=CONVERSATION,
        contact_id=CONTACT,
        contact_phone="573001112233",
        status=status,
        text=text,
    )


@pytest.mark.asyncio
async def test_opting_in_costs_no_model_call() -> None:
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    handled = await _service(metered, channel, repo).handle_inbound(
        _inbound(STATUS_GREETED, "1"), []
    )
    assert handled
    assert channel.statuses == [STATUS_BOT]
    assert metered.calls == 0, "aceptar el asistente no debe costar una llamada"


@pytest.mark.asyncio
async def test_asking_for_a_human_costs_no_model_call() -> None:
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    handled = await _service(metered, channel, repo).handle_inbound(
        _inbound(STATUS_BOT, "quiero hablar con una persona"), []
    )
    assert handled
    assert channel.statuses == [STATUS_HUMAN]
    assert metered.calls == 0, "quien pide un humano ya no quiere otra respuesta automática"


@pytest.mark.asyncio
async def test_a_greeted_conversation_is_not_hijacked() -> None:
    """Escribir cualquier cosa tras el saludo NO mete a nadie en el bot."""
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    handled = await _service(metered, channel, repo).handle_inbound(
        _inbound(STATUS_GREETED, "hola, ¿tienen domicilio?"), []
    )
    assert not handled
    assert channel.statuses == [] and channel.sent == [] and metered.calls == 0


@pytest.mark.asyncio
async def test_bot_turn_answers_and_remembers() -> None:
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    service = _service(metered, channel, repo)
    assert await service.handle_inbound(_inbound(STATUS_BOT, "¿a qué hora abren?"), [])
    assert metered.calls == 1
    assert channel.sent == ["Abrimos a las 11."]

    state = repo.states[f"whatsapp:{CONVERSATION}"]
    assert [t.role for t in state.turns] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_history_is_a_fixed_window() -> None:
    """La historia es el principal motor del coste de entrada: se recorta al guardar."""
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    service = _service(metered, channel, repo, history=4)
    for i in range(5):
        await service.handle_inbound(_inbound(STATUS_BOT, f"pregunta {i}"), [])

    state = repo.states[f"whatsapp:{CONVERSATION}"]
    assert len(state.turns) == 4
    assert state.turns[0].text == "pregunta 3"
    # Y lo que se manda al modelo es lo guardado, no la conversación entera.
    assert len(metered.last_turns) == 4


@pytest.mark.asyncio
async def test_a_business_without_the_assistant_never_enters_bot_mode() -> None:
    """El saludo puede ofrecerlo y el negocio no tenerlo: entonces contesta una persona.

    Cambiar el estado igualmente dejaría al cliente escribiéndole a algo que no responde —
    silencio con pinta de avería— cuando lo correcto es exactamente lo que pasaba sin la
    oferta: que lo atienda alguien.
    """
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo(entitled=False)
    handled = await _service(metered, channel, repo).handle_inbound(
        _inbound(STATUS_GREETED, "1"), []
    )
    assert not handled
    assert channel.statuses == [] and channel.sent == [] and metered.calls == 0


# --- Cerrado: la puerta de entrada también se cierra -------------------------
@pytest.mark.asyncio
async def test_a_closed_business_does_not_hand_anyone_to_the_bot() -> None:
    """Con el negocio cerrado, "1" no entra al asistente.

    Fuera de horario el asistente no contesta, así que meter la conversación en modo bot la
    cambiaría de dueño para que siga sin contestarle nadie — y la sacaría de la cola de lo que
    una persona atiende al abrir. Se queda en `greeted`.
    """
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    handled = await _service(
        metered, channel, repo, hours=FakeHours(open_now=False, next_opening=(1, 8 * 60))
    ).handle_inbound(_inbound(STATUS_GREETED, "1"), [])

    assert not handled
    assert channel.statuses == [], "no se entra en modo bot con el negocio cerrado"
    # Y ni una palabra: el saludo de cerrado ya dijo a qué hora abrimos, y repetirlo es el bot
    # diciendo dos veces lo mismo.
    assert channel.sent == []
    assert metered.calls == 0


@pytest.mark.asyncio
async def test_the_opt_in_still_works_once_the_business_opens() -> None:
    """La conversación sigue en `greeted`, así que el "1" del día siguiente sí entra."""
    metered, channel, repo = FakeMetered(), FakeChannel(), FakeRepo()
    service = _service(metered, channel, repo, hours=FakeHours(open_now=True))

    assert await service.handle_inbound(_inbound(STATUS_GREETED, "1"), [])
    assert channel.statuses == [STATUS_BOT]
    assert metered.calls == 0
