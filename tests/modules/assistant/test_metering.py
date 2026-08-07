"""El punto de estrangulamiento: lo que cobra, lo que rechaza y en qué orden.

La afirmación que se repite en casi todas las pruebas es la misma y es la que importa:
**cuántas veces llegó la petición al motor**. Un límite que rechaza pero llama igual no es un
límite, es un log; y como aquí el que paga somos nosotros, la diferencia se mide en dinero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from restaurante.modules.assistant.application.use_cases.metering import (
    CHARS_PER_TOKEN,
    CallerContext,
    MeteredAssistant,
)
from restaurante.modules.assistant.domain.entities import (
    CALLER_CUSTOMER,
    AssistantConversationState,
    AssistantEntitlement,
    ConversationTurn,
    UsageEntry,
)
from restaurante.modules.assistant.domain.errors import (
    AssistantDisabledError,
    AssistantNotEntitledError,
    AssistantProviderError,
    QuotaExhaustedError,
    RateLimitedError,
)
from restaurante.modules.assistant.domain.plans import PLANS, resolve_plan
from restaurante.modules.assistant.domain.ports import (
    EngineReply,
    EngineRequest,
    NullKnowledgeIndex,
    Passage,
    ToolSpec,
)

TENANT = uuid.uuid4()


class FakeEngine:
    """Cuenta llamadas y guarda lo que se le pidió. Es el testigo de casi todo."""

    def __init__(self, tokens: tuple[int, int] = (100, 50)) -> None:
        self.calls = 0
        self.requests: list[EngineRequest] = []
        self._tokens = tokens

    async def respond(self, request: EngineRequest) -> EngineReply:
        self.calls += 1
        self.requests.append(request)
        return EngineReply(
            text="ok", tokens_in=self._tokens[0], tokens_out=self._tokens[1]
        )


class ExplodingEngine:
    """Falla DESPUÉS de haber consumido tokens, que es el caso que se olvida."""

    def __init__(self, tokens: tuple[int, int] = (80, 20)) -> None:
        self.calls = 0
        self._tokens = tokens

    async def respond(self, request: EngineRequest) -> EngineReply:
        self.calls += 1
        raise AssistantProviderError(
            "el proveedor se cayó", tokens_in=self._tokens[0], tokens_out=self._tokens[1]
        )


class MemoryRepo:
    def __init__(self, entitlement: AssistantEntitlement | None) -> None:
        self._entitlement = entitlement
        self.ledger: list[UsageEntry] = []
        self.states: dict[str, AssistantConversationState] = {}

    async def get_entitlement(self, tenant_id: uuid.UUID) -> AssistantEntitlement | None:
        return self._entitlement

    async def save_entitlement(self, entitlement: AssistantEntitlement) -> Any:
        self._entitlement = entitlement
        return entitlement

    async def record_usage(self, entry: UsageEntry) -> UsageEntry:
        entry.id = uuid.uuid4()
        self.ledger.append(entry)
        return entry

    async def units_used(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> int:
        return sum(
            e.billed_units
            for e in self.ledger
            if period_start <= e.occurred_at < period_end
        )

    async def usage_cost(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> Decimal:
        return sum(
            (e.provider_cost for e in self.ledger), Decimal(0)
        )

    async def recent_usage(self, tenant_id: uuid.UUID, limit: int = 20) -> list[UsageEntry]:
        return self.ledger[-limit:]

    async def get_state(self, tenant_id: uuid.UUID, ref: str) -> Any:
        return self.states.get(ref)

    async def save_state(self, state: AssistantConversationState) -> Any:
        self.states[state.conversation_ref] = state
        return state


class AlwaysAllows:
    def __init__(self) -> None:
        self.hits = 0

    async def hit(self, tenant_id: uuid.UUID, limit_per_minute: int) -> bool:
        self.hits += 1
        return True


class AlwaysRefuses:
    async def hit(self, tenant_id: uuid.UUID, limit_per_minute: int) -> bool:
        return False


class LoadedIndex:
    """Un índice con material que SE PARECE a lo que preguntan."""

    async def retrieve(
        self, tenant_id: uuid.UUID, query: str, limit: int = 4
    ) -> list[Passage]:
        return [Passage(text="Abrimos de 9 a 5 (folleto de 2019)", source="folleto")]


def _entitlement(**kwargs: Any) -> AssistantEntitlement:
    defaults: dict[str, Any] = {
        "tenant_id": TENANT,
        "plan": "basic",
        "is_enabled": True,
        "monthly_quota_units": 100,
        "period_anchor": datetime.now(UTC) - timedelta(days=3),
    }
    defaults.update(kwargs)
    return AssistantEntitlement(**defaults)


#: "No se pasó nada" y "se pasó `None`" son cosas distintas aquí: `None` ES el caso de un
#: tenant sin derecho, y con un `None` por defecto ese caso no se podía escribir.
_DEFAULT = object()


def _service(
    engine: Any,
    entitlement: Any = _DEFAULT,
    *,
    limiter: Any = None,
    index: Any = None,
    kill_switch: bool = False,
) -> tuple[MeteredAssistant, MemoryRepo]:
    repo = MemoryRepo(_entitlement() if entitlement is _DEFAULT else entitlement)
    service = MeteredAssistant(
        repo,  # type: ignore[arg-type]
        engine,
        index or NullKnowledgeIndex(),
        limiter or AlwaysAllows(),
        kill_switch=kill_switch,
    )
    return service, repo


def _caller() -> CallerContext:
    return CallerContext(tenant_id=TENANT, caller_kind=CALLER_CUSTOMER)


async def _ask(service: MeteredAssistant, question: str = "¿a qué hora abren?") -> Any:
    return await service.ask(_caller(), question, system_prompt="eres un asistente")


# --- Las cuatro puertas ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_unentitled_tenant_never_reaches_the_model() -> None:
    engine = FakeEngine()
    service, repo = _service(engine, entitlement=None)
    with pytest.raises(AssistantNotEntitledError):
        await _ask(service)
    assert engine.calls == 0 and repo.ledger == []


@pytest.mark.asyncio
async def test_a_disabled_entitlement_never_reaches_the_model() -> None:
    engine = FakeEngine()
    service, _ = _service(engine, _entitlement(is_enabled=False))
    with pytest.raises(AssistantNotEntitledError):
        await _ask(service)
    assert engine.calls == 0


@pytest.mark.asyncio
async def test_the_kill_switch_beats_everything() -> None:
    """Global, nuestro, y ANTES que cualquier lectura: no depende de que la base conteste."""
    engine = FakeEngine()
    service, _ = _service(engine, _entitlement(monthly_quota_units=10_000), kill_switch=True)
    with pytest.raises(AssistantDisabledError):
        await _ask(service)
    assert engine.calls == 0


@pytest.mark.asyncio
async def test_the_rate_limit_refuses_without_consuming_quota() -> None:
    """Cobrarle a alguien el mensaje que no le contestamos es cobrarle nuestra defensa."""
    engine = FakeEngine()
    service, repo = _service(engine, limiter=AlwaysRefuses())
    with pytest.raises(RateLimitedError):
        await _ask(service)
    assert engine.calls == 0
    assert repo.ledger == [], "un rechazo por minuto no puede aparecer en el libro"


@pytest.mark.asyncio
async def test_the_quota_refuses_inside_the_rate_limit() -> None:
    limiter = AlwaysAllows()
    engine = FakeEngine()
    service, repo = _service(engine, _entitlement(monthly_quota_units=1), limiter=limiter)

    await _ask(service)  # gasta la única unidad
    with pytest.raises(QuotaExhaustedError):
        await _ask(service)

    assert engine.calls == 1
    assert len(repo.ledger) == 1
    assert limiter.hits == 2, "el límite por minuto se consultó, y aun así mandó la cuota"


# --- El libro ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_ledger_has_both_cost_layers() -> None:
    engine = FakeEngine(tokens=(1000, 500))
    service, repo = _service(engine)
    await _ask(service)

    entry = repo.ledger[0]
    plan = resolve_plan("basic")
    assert entry.billed_units == 1, "lo que se le factura al tenant"
    assert entry.provider_cost == plan.cost(1000, 500), "lo que nos costó a nosotros"
    assert entry.provider_cost > 0
    assert entry.model == plan.model and entry.provider == plan.provider


@pytest.mark.asyncio
async def test_the_ledger_is_written_even_when_the_provider_fails() -> None:
    """Lo que se pagó, se apunta. Si no, el libro deja de cuadrar en los casos raros."""
    engine = ExplodingEngine(tokens=(80, 20))
    service, repo = _service(engine)
    with pytest.raises(AssistantProviderError):
        await _ask(service)

    assert len(repo.ledger) == 1
    assert (repo.ledger[0].tokens_in, repo.ledger[0].tokens_out) == (80, 20)


@pytest.mark.asyncio
async def test_a_failure_that_consumed_nothing_writes_nothing() -> None:
    engine = ExplodingEngine(tokens=(0, 0))
    service, repo = _service(engine)
    with pytest.raises(AssistantProviderError):
        await _ask(service)
    assert repo.ledger == []


@pytest.mark.asyncio
async def test_the_balance_is_a_projection_over_the_ledger() -> None:
    service, repo = _service(FakeEngine())
    for _ in range(3):
        await _ask(service)

    status = await service.usage_status(TENANT)
    assert status.used_units == 3 == len(repo.ledger)
    assert status.remaining_units == 97
    assert not status.exhausted


# --- Los techos --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_oversized_input_is_truncated_before_it_costs_anything() -> None:
    engine = FakeEngine()
    service, _ = _service(engine)
    plan = resolve_plan("basic")

    await _ask(service, "a" * 50_000)

    sent = engine.requests[0]
    assert len(sent.question) <= plan.max_input_tokens * CHARS_PER_TOKEN
    assert sent.max_output_tokens == plan.max_output_tokens


@pytest.mark.asyncio
async def test_history_is_dropped_before_the_question() -> None:
    """La pregunta es lo que hay que contestar; la historia es contexto prescindible."""
    engine = FakeEngine()
    service, _ = _service(engine)
    huge = [ConversationTurn("user", "b" * 20_000)]

    await service.ask(
        _caller(), "¿abren hoy?", system_prompt="x", turns=huge
    )

    sent = engine.requests[0]
    assert sent.question == "¿abren hoy?"
    assert sent.turns == [], "no cabía: se cae la historia, no la pregunta"


@pytest.mark.asyncio
async def test_the_overshoot_is_at_most_one_call() -> None:
    """La cuota se comprueba antes y se apunta después, así que puede pasarse — pero sólo
    por una llamada, y con los techos del plan eso es una cifra exacta."""
    engine = FakeEngine()
    service, repo = _service(engine, _entitlement(monthly_quota_units=2))
    await _ask(service)
    await _ask(service)
    with pytest.raises(QuotaExhaustedError):
        await _ask(service)

    plan = resolve_plan("basic")
    spent = sum((e.provider_cost for e in repo.ledger), Decimal(0))
    assert spent <= plan.max_cost_per_call * 2


# --- El índice ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_it_works_with_the_null_index() -> None:
    engine = FakeEngine()
    service, _ = _service(engine, index=NullKnowledgeIndex())
    await _ask(service)
    assert engine.requests[0].passages == []


@pytest.mark.asyncio
async def test_a_populated_index_does_not_replace_the_tools() -> None:
    """Al índice no se le pregunta lo que sabe la base.

    Aunque el índice traiga algo que se PARECE a la respuesta (un folleto viejo con otro
    horario), las herramientas siguen yendo: son ellas las que tienen el dato vivo.
    """
    engine = FakeEngine()
    service, _ = _service(engine, index=LoadedIndex())
    tool = ToolSpec(
        name="branch_hours", description="horario", parameters={}, run=_noop
    )
    await service.ask(_caller(), "¿a qué hora cierran?", system_prompt="x", tools=[tool])

    sent = engine.requests[0]
    assert [t.name for t in sent.tools] == ["branch_hours"]
    assert sent.passages and sent.passages[0].source == "folleto"


async def _noop(args: dict[str, Any]) -> str:
    return ""


# --- El plan -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_plan_picks_the_model() -> None:
    engine = FakeEngine()
    service, _ = _service(engine, _entitlement(plan="max"))
    await _ask(service)
    assert engine.requests[0].model == PLANS["max"].model


@pytest.mark.asyncio
async def test_an_unknown_plan_falls_back_to_a_capped_one() -> None:
    """Un plan viejo en una fila no puede convertirse en una llamada sin techo."""
    engine = FakeEngine()
    service, _ = _service(engine, _entitlement(plan="plan-que-ya-no-existe"))
    await _ask(service)

    sent = engine.requests[0]
    assert sent.model == PLANS["basic"].model
    assert sent.max_output_tokens == PLANS["basic"].max_output_tokens
