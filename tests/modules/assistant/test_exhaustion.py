"""Agotamiento: se degrada, no falla. Y sobre todo, **sin llamar al modelo**.

La afirmación central es un contador a cero: explicar que se acabó el saldo pidiéndoselo al
modelo cuesta justo la llamada que no hay con qué pagar, y sería la llamada que se hace
precisamente cuando el tenant ya se pasó de lo que compró.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from restaurante.modules.alerts.application.use_cases.evaluators import (
    AssistantQuotaEvaluator,
)
from restaurante.modules.alerts.domain.entities import RULE_ASSISTANT_QUOTA, AlertRule
from restaurante.modules.alerts.domain.ports import QuotaLevel
from restaurante.modules.assistant.application.use_cases.conversation import (
    DEFAULT_FALLBACK,
    STATUS_BOT,
    AssistantConversationService,
    InboundContext,
)
from restaurante.modules.assistant.domain.entities import AssistantEntitlement
from restaurante.modules.assistant.domain.errors import QuotaExhaustedError

from .test_conversation_flow import BRANCH, CONTACT, CONVERSATION, TENANT, FakeChannel


class ExhaustedMetered:
    def __init__(self) -> None:
        self.calls = 0

    async def ask(self, caller: Any, question: str, **kwargs: Any) -> Any:
        self.calls += 1
        raise QuotaExhaustedError()


class RepoWithEntitlement:
    def __init__(self, fallback: str = "") -> None:
        self.entitlement = AssistantEntitlement(tenant_id=TENANT, fallback_message=fallback)
        self.saved: list[Any] = []

    async def get_entitlement(self, tenant_id: uuid.UUID) -> AssistantEntitlement:
        return self.entitlement

    async def get_state(self, tenant_id: uuid.UUID, ref: str) -> None:
        return None

    async def save_state(self, state: Any) -> Any:
        self.saved.append(state)
        return state


def _inbound() -> InboundContext:
    return InboundContext(
        tenant_id=TENANT,
        branch_id=BRANCH,
        conversation_id=CONVERSATION,
        contact_id=CONTACT,
        contact_phone="573001112233",
        status=STATUS_BOT,
        text="¿a qué hora abren?",
    )


@pytest.mark.asyncio
async def test_exhausted_quota_answers_without_a_second_model_call() -> None:
    metered, channel, repo = ExhaustedMetered(), FakeChannel(), RepoWithEntitlement()
    service = AssistantConversationService(
        cast(Any, metered), cast(Any, repo), cast(Any, channel)
    )

    assert await service.handle_inbound(_inbound(), [])
    # Una sola: la que descubrió que no había saldo. Ninguna para redactar la disculpa.
    assert metered.calls == 1
    assert len(channel.sent) == 1
    assert "store" in channel.sent[0]
    assert DEFAULT_FALLBACK.split("{link}")[0].strip() in channel.sent[0]


@pytest.mark.asyncio
async def test_the_conversation_stays_claimable() -> None:
    """Tras el mensaje de agotamiento nadie cierra ni aparta la conversación."""
    metered, channel, repo = ExhaustedMetered(), FakeChannel(), RepoWithEntitlement()
    service = AssistantConversationService(
        cast(Any, metered), cast(Any, repo), cast(Any, channel)
    )
    await service.handle_inbound(_inbound(), [])
    assert channel.statuses == [], "cerrarla la sacaría del inbox y nadie podría tomarla"


@pytest.mark.asyncio
async def test_tenant_text_wins_over_the_factory_one() -> None:
    metered, channel = ExhaustedMetered(), FakeChannel()
    repo = RepoWithEntitlement(fallback="Escríbenos y te atendemos: {link}")
    service = AssistantConversationService(
        cast(Any, metered), cast(Any, repo), cast(Any, channel)
    )
    await service.handle_inbound(_inbound(), [])
    assert channel.sent[0].startswith("Escríbenos")
    assert "{link}" not in channel.sent[0]


# --- La regla de aviso, sobre la maquinaria de alertas ------------------------------------


class FakeQuotaReader:
    def __init__(self, level: QuotaLevel | None) -> None:
        self._level = level

    async def quota(self, tenant_id: uuid.UUID) -> QuotaLevel | None:
        return self._level


def _rule(recovery_buffer: float = 5) -> AlertRule:
    return AlertRule(
        tenant_id=TENANT,
        branch_id=BRANCH,
        rule_key=RULE_ASSISTANT_QUOTA,
        is_enabled=True,
        recovery_buffer=recovery_buffer,
    )


@pytest.mark.asyncio
async def test_warning_fires_at_the_owners_threshold() -> None:
    evaluator = AssistantQuotaEvaluator(
        cast(Any, FakeQuotaReader(QuotaLevel(82.0, 820, 1000, 80)))
    )
    result = await evaluator.evaluate(_rule())
    assert [s.ref for s in result.firing] == [str(TENANT)]
    assert "820 de 1000" in result.firing[0].detail


@pytest.mark.asyncio
async def test_below_the_threshold_says_nothing() -> None:
    evaluator = AssistantQuotaEvaluator(
        cast(Any, FakeQuotaReader(QuotaLevel(50.0, 500, 1000, 80)))
    )
    assert (await evaluator.evaluate(_rule())).firing == []


@pytest.mark.asyncio
async def test_a_new_period_re_arms_it() -> None:
    """El periodo nuevo vuelve el consumo a cero y la histéresis de siempre lo re-arma.

    No hay ninguna lógica de "¿es otro mes?" — que es exactamente el código que no hay que
    escribir cuando la maquinaria de alertas ya resuelve esto.
    """
    evaluator = AssistantQuotaEvaluator(
        cast(Any, FakeQuotaReader(QuotaLevel(2.0, 20, 1000, 80)))
    )
    result = await evaluator.evaluate(_rule(), open_refs=[str(TENANT)])
    assert result.cleared == [str(TENANT)]


@pytest.mark.asyncio
async def test_a_tenant_without_the_assistant_is_never_warned() -> None:
    evaluator = AssistantQuotaEvaluator(cast(Any, FakeQuotaReader(None)))
    result = await evaluator.evaluate(_rule(), open_refs=[])
    assert result.firing == []
