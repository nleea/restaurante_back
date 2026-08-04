"""El punto de estrangulamiento. **Toda** llamada al modelo pasa por aquí.

    interruptor global → derecho → límite por minuto → cuota → LLAMADA → libro mayor

Una sola puerta, por el mismo motivo que `open_order` es la única puerta de la caja: dos
puertas significa que una de las dos no está medida, y será la que alguien añada con prisa.

El orden no es decorativo:

- **El interruptor global va primero** aunque la tarea lo listara en segundo lugar. Es
  nuestro y global; hacerlo depender de una consulta a la base sería que "para todo ahora
  mismo" necesite que la base conteste.
- **Rechazar por límite de minuto no consume cuota.** Cobrarle a alguien por el mensaje que
  no le contestamos es cobrarle por nuestra propia defensa.
- **La cuota se comprueba antes y se apunta después.** Por eso puede desbordarse — como
  mucho por UNA llamada, y con los techos del plan eso es una cifra exacta, no un
  encogimiento de hombros.
- **El libro se escribe incluso si el proveedor falla**, siempre que llegara a consumir
  tokens: lo que se pagó, se apunta.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from restaurante.modules.assistant.domain.entities import (
    UNITS_PER_CALL,
    AssistantEntitlement,
    ConversationTurn,
    UsageEntry,
    period_bounds,
)
from restaurante.modules.assistant.domain.errors import (
    AssistantDisabledError,
    AssistantNotEntitledError,
    AssistantProviderError,
    QuotaExhaustedError,
    RateLimitedError,
)
from restaurante.modules.assistant.domain.plans import PlanSpec, resolve_plan
from restaurante.modules.assistant.domain.ports import (
    AssistantRepository,
    ConversationEngine,
    EngineRequest,
    KnowledgeIndex,
    RateLimiter,
    ToolSpec,
)

logger = logging.getLogger(__name__)

#: Caracteres por token, para recortar la entrada sin arrastrar un tokenizador.
#:
#: Es una ESTIMACIÓN, y por eso es conservadora: el techo existe para acotar el gasto, así
#: que equivocarse recortando de más cuesta una respuesta con menos contexto, y equivocarse
#: recortando de menos cuesta dinero. La cifra real se apunta luego en el libro: la que
#: manda para la factura es la del proveedor, nunca esta.
CHARS_PER_TOKEN = 4


@dataclass
class CallerContext:
    """Quién pregunta. Determina el registro de herramientas, y con él lo que puede saberse."""

    tenant_id: uuid.UUID
    caller_kind: str
    conversation_ref: str | None = None
    branch_id: uuid.UUID | None = None


@dataclass
class AssistantAnswer:
    """La respuesta y lo que costó darla."""

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    provider_cost: Decimal
    billed_units: int


@dataclass
class UsageStatus:
    """El saldo del periodo. Lo que pinta la pantalla de consumo y lo que mira la alerta."""

    entitled: bool
    is_enabled: bool
    plan: str
    quota_units: int
    used_units: int
    period_start: datetime | None
    period_end: datetime | None
    provider_cost: Decimal = Decimal("0")
    warning_threshold_percent: int = 0

    @property
    def remaining_units(self) -> int:
        return max(0, self.quota_units - self.used_units)

    @property
    def used_percent(self) -> float:
        if self.quota_units <= 0:
            return 100.0
        return round(self.used_units * 100 / self.quota_units, 2)

    @property
    def exhausted(self) -> bool:
        return self.remaining_units <= 0


class MeteredAssistant:
    def __init__(
        self,
        repo: AssistantRepository,
        engine: ConversationEngine,
        index: KnowledgeIndex,
        limiter: RateLimiter,
        *,
        kill_switch: bool = False,
        rate_limit_per_minute: int = 10,
    ) -> None:
        self._repo = repo
        self._engine = engine
        self._index = index
        self._limiter = limiter
        self._kill_switch = kill_switch
        self._rate_limit = rate_limit_per_minute

    # --- Lecturas -----------------------------------------------------------
    async def usage_status(self, tenant_id: uuid.UUID) -> UsageStatus:
        """El saldo, sin llamar a nadie. La proyección sobre el libro, no un contador."""
        entitlement = await self._repo.get_entitlement(tenant_id)
        if entitlement is None:
            return UsageStatus(
                entitled=False,
                is_enabled=False,
                plan="",
                quota_units=0,
                used_units=0,
                period_start=None,
                period_end=None,
            )
        start, end = self._period(entitlement)
        return UsageStatus(
            entitled=True,
            is_enabled=entitlement.is_enabled,
            plan=entitlement.plan,
            quota_units=entitlement.monthly_quota_units,
            used_units=await self._repo.units_used(tenant_id, start, end),
            period_start=start,
            period_end=end,
            provider_cost=await self._repo.usage_cost(tenant_id, start, end),
            warning_threshold_percent=entitlement.warning_threshold_percent,
        )

    # --- La única puerta ----------------------------------------------------
    async def ask(
        self,
        caller: CallerContext,
        question: str,
        *,
        system_prompt: str,
        tools: list[ToolSpec] | None = None,
        turns: list[ConversationTurn] | None = None,
    ) -> AssistantAnswer:
        """Contesta cobrando. Es el ÚNICO método que puede llegar al motor."""
        # 1. El interruptor global. Antes que nada y sin mirar la base.
        if self._kill_switch:
            raise AssistantDisabledError()

        # 2. El derecho. Sin fila, el asistente no existe para este negocio.
        entitlement = await self._repo.get_entitlement(caller.tenant_id)
        if entitlement is None or not entitlement.is_enabled:
            raise AssistantNotEntitledError()
        plan = resolve_plan(entitlement.plan)

        # 3. El límite por minuto. Rechazar aquí NO consume cuota.
        if not await self._limiter.hit(caller.tenant_id, self._rate_limit):
            raise RateLimitedError()

        # 4. La cuota. Se comprueba antes; se apunta después.
        start, end = self._period(entitlement)
        used = await self._repo.units_used(caller.tenant_id, start, end)
        if used + UNITS_PER_CALL > entitlement.monthly_quota_units:
            raise QuotaExhaustedError()

        # 5. El índice. Hoy no devuelve nada, y el asistente contesta con herramientas.
        passages = await self._index.retrieve(caller.tenant_id, question)

        # 6. Los techos, para que el coste máximo de esta llamada ya se conozca.
        trimmed_question, trimmed_turns = self._fit_input(question, turns or [], plan)

        request = EngineRequest(
            provider=plan.provider,
            model=plan.model,
            system_prompt=system_prompt,
            question=trimmed_question,
            turns=trimmed_turns,
            tools=tools or [],
            passages=passages,
            max_output_tokens=plan.max_output_tokens,
            reasoning_effort=plan.reasoning_effort,
        )

        # 7. La llamada, y el libro pase lo que pase.
        try:
            reply = await self._engine.respond(request)
        except AssistantProviderError as exc:
            if exc.tokens_in or exc.tokens_out:
                # Se consumió: se apunta. Un fallo que gastó y no aparece en el libro es el
                # tipo de diferencia que sólo se descubre en la factura del proveedor.
                await self._record(caller, plan, exc.tokens_in, exc.tokens_out)
            raise

        return await self._record(caller, plan, reply.tokens_in, reply.tokens_out, reply.text)

    # --- Interno ------------------------------------------------------------
    async def _record(
        self,
        caller: CallerContext,
        plan: PlanSpec,
        tokens_in: int,
        tokens_out: int,
        text: str = "",
    ) -> AssistantAnswer:
        cost = plan.cost(tokens_in, tokens_out)
        await self._repo.record_usage(
            UsageEntry(
                tenant_id=caller.tenant_id,
                occurred_at=datetime.now(UTC),
                caller_kind=caller.caller_kind,
                conversation_ref=caller.conversation_ref,
                provider=plan.provider,
                model=plan.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                provider_cost=cost,
                billed_units=UNITS_PER_CALL,
            )
        )
        return AssistantAnswer(
            text=text,
            model=plan.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            provider_cost=cost,
            billed_units=UNITS_PER_CALL,
        )

    def _fit_input(
        self, question: str, turns: list[ConversationTurn], plan: PlanSpec
    ) -> tuple[str, list[ConversationTurn]]:
        """Recorta hasta caber en `max_input_tokens`. La pregunta manda sobre la historia.

        La entrada la escribe un desconocido: 5.000 caracteres por WhatsApp son gratis para
        él y no para nosotros. Se descarta historia antes que pregunta —el turno de ahora es
        lo que hay que contestar— y sólo si aun así no cabe se corta la pregunta.
        """
        budget = plan.max_input_tokens * CHARS_PER_TOKEN
        clipped_question = question[:budget]
        remaining = budget - len(clipped_question)

        kept: list[ConversationTurn] = []
        for turn in reversed(turns):  # de lo más reciente a lo más viejo
            if len(turn.text) > remaining:
                break
            kept.append(turn)
            remaining -= len(turn.text)
        kept.reverse()
        return clipped_question, kept

    def _period(self, entitlement: AssistantEntitlement) -> tuple[datetime, datetime]:
        anchor = entitlement.period_anchor or datetime.now(UTC)
        return period_bounds(anchor, datetime.now(UTC))
