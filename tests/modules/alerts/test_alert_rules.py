"""Las reglas y el barrido.

Lo que se prueba no es "¿detecta?" sino las dos propiedades que hacen que el módulo siga
vivo dentro de un mes: **la histéresis** (un valor que oscila en el umbral produce UNA
alerta, no cuarenta) y que **el barrido es autoritativo** (quita el camino del job entero y
el sistema sigue siendo correcto).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from restaurante.modules.alerts.application.use_cases.evaluators import (
    CashSessionLeftOpenEvaluator,
    LowStockEvaluator,
    WhatsAppSessionDownEvaluator,
    build_registry,
)
from restaurante.modules.alerts.application.use_cases.lifecycle import AlertLifecycle
from restaurante.modules.alerts.application.use_cases.sweep import AlertSweeper
from restaurante.modules.alerts.domain.entities import (
    RULE_CASH_SESSION_LEFT_OPEN,
    RULE_LOW_STOCK,
    RULE_WHATSAPP_SESSION_DOWN,
    AlertRule,
)
from restaurante.modules.alerts.domain.ports import (
    OpenCashSession,
    SessionState,
    StockLevel,
)
from restaurante.modules.alerts.infrastructure.repositories import (
    SqlAlchemyAlertRepository,
)
from restaurante.modules.business.application.clock import now_local
from tests.modules.alerts.conftest import (
    RecordingChannel,
    demo_tenant_id,
    tracked_session,
)

pytestmark = pytest.mark.asyncio


# --- Dobles de lectura ------------------------------------------------------
# Triviales a propósito: lo que se prueba es la REGLA, no la consulta SQL. Las consultas
# viven en `readers.py` y son `SELECT` sin lógica.
class FakeInventory:
    def __init__(self, levels: list[StockLevel]) -> None:
        self.levels = levels

    async def low_stock(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> list[StockLevel]:
        return [s for s in self.levels if s.current <= s.minimum]

    async def stock_for(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_ids: list[str]
    ) -> list[StockLevel]:
        return [s for s in self.levels if s.ingredient_id in ingredient_ids]


class FakeSessions:
    def __init__(self, states: list[SessionState]) -> None:
        self.states = states

    async def sessions(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> list[SessionState]:
        return self.states


class FakeCash:
    def __init__(self, session: OpenCashSession | None) -> None:
        self.session = session

    async def open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> OpenCashSession | None:
        return self.session


def _rule(key: str, **over: object) -> AlertRule:
    fields: dict[str, object] = {"is_enabled": True, "recovery_buffer": 2, **over}
    return AlertRule(
        tenant_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        rule_key=key,
        **fields,  # type: ignore[arg-type]
    )


TOMATO = "11111111-1111-1111-1111-111111111111"
CHEESE = "22222222-2222-2222-2222-222222222222"


# --- Stock bajo -------------------------------------------------------------
async def test_low_stock_fires_per_ingredient() -> None:
    inventory = FakeInventory(
        [
            StockLevel(TOMATO, "Tomate", current=2, minimum=10),
            StockLevel(CHEESE, "Queso", current=1, minimum=5),
        ]
    )

    result = await LowStockEvaluator(inventory).evaluate(_rule(RULE_LOW_STOCK))

    # Quedarse sin tomate no puede tapar que también falta queso.
    assert {s.ref for s in result.firing} == {TOMATO, CHEESE}
    assert "Tomate" in [s.label for s in result.firing]


async def test_an_ingredient_without_a_minimum_never_fires() -> None:
    """Sin mínimo configurado, `0 <= 0` sería siempre cierto.

    Encender la regla avisaría de TODO el catálogo el primer día, que es la forma más rápida
    de que alguien la apague para siempre.
    """
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=0, minimum=0)])

    result = await LowStockEvaluator(inventory).evaluate(_rule(RULE_LOW_STOCK))

    assert result.firing == []


async def test_returning_to_the_threshold_does_not_re_arm() -> None:
    """Volver justo al mínimo NO recupera: al primer gramo que salga volvería a disparar."""
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=10, minimum=10)])
    rule = _rule(RULE_LOW_STOCK, recovery_buffer=2)

    result = await LowStockEvaluator(inventory).evaluate(rule, open_refs=[TOMATO])

    assert result.cleared == []


async def test_clearing_past_the_buffer_re_arms() -> None:
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=13, minimum=10)])
    rule = _rule(RULE_LOW_STOCK, recovery_buffer=2)

    result = await LowStockEvaluator(inventory).evaluate(rule, open_refs=[TOMATO])

    # 13 > 10 + 2. Repuesto de verdad, no rozando la frontera.
    assert result.cleared == [TOMATO]
    assert result.firing == []


async def test_just_inside_the_buffer_still_does_not_re_arm() -> None:
    # 12 no es > 12 (mínimo 10 + 20%). El límite es estricto a propósito: "exactamente en el
    # borde" es justamente el valor que oscila.
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=12, minimum=10)])
    result = await LowStockEvaluator(inventory).evaluate(
        _rule(RULE_LOW_STOCK, recovery_buffer=20), open_refs=[TOMATO]
    )
    assert result.cleared == []


# --- El colchón es un PORCENTAJE del mínimo ----------------------------------
# Es la razón entera de que el colchón dejara de ser una cantidad: los sujetos de esta regla son
# insumos con unidades de medida distintas entre sí, así que un número absoluto significa cosas
# distintas para cada uno. Estos dos casos son los dos extremos que el `1` absoluto rompía.
async def test_a_small_minimum_does_not_demand_a_huge_restock() -> None:
    """Camarón: mínimo 2 kg. Con el colchón absoluto de 1 había que llegar a 3 kg — un 50% de más.

    Es el caso que motivó el cambio: reponer por encima del mínimo y seguir viendo la alerta.
    """
    inventory = FakeInventory([StockLevel(TOMATO, "Camarón", current=2.3, minimum=2)])

    result = await LowStockEvaluator(inventory).evaluate(
        _rule(RULE_LOW_STOCK, recovery_buffer=10), open_refs=[TOMATO]
    )

    # 2.3 > 2 * 1.10 = 2.2
    assert result.cleared == [TOMATO]


async def test_a_large_minimum_is_not_cleared_by_a_crumb() -> None:
    """Sal: mínimo 500 g. Con el colchón absoluto de 1, UN GRAMO cerraba la alerta."""
    inventory = FakeInventory([StockLevel(TOMATO, "Sal", current=501, minimum=500)])

    result = await LowStockEvaluator(inventory).evaluate(
        _rule(RULE_LOW_STOCK, recovery_buffer=10), open_refs=[TOMATO]
    )

    # 501 no es > 550. Un gramo sobre medio kilo no es haberse repuesto.
    assert result.cleared == []


async def test_the_same_percentage_works_for_both_scales() -> None:
    """La propiedad que se compró: un mismo colchón sirve para insumos incomparables."""
    inventory = FakeInventory(
        [
            StockLevel(TOMATO, "Camarón (kg)", current=2.5, minimum=2),
            StockLevel(CHEESE, "Sal (g)", current=625, minimum=500),
        ]
    )

    result = await LowStockEvaluator(inventory).evaluate(
        _rule(RULE_LOW_STOCK, recovery_buffer=10), open_refs=[TOMATO, CHEESE]
    )

    # Los dos están un 25% por encima de su mínimo, midan kilos o gramos.
    assert set(result.cleared) == {TOMATO, CHEESE}


async def test_the_job_path_looks_at_one_ingredient_only() -> None:
    inventory = FakeInventory(
        [
            StockLevel(TOMATO, "Tomate", current=2, minimum=10),
            StockLevel(CHEESE, "Queso", current=1, minimum=5),
        ]
    )

    result = await LowStockEvaluator(inventory).evaluate(_rule(RULE_LOW_STOCK), subject_ref=TOMATO)

    # El job gana latencia mirando sólo lo que se acaba de mover.
    assert [s.ref for s in result.firing] == [TOMATO]


# --- Sesión de WhatsApp caída ------------------------------------------------
async def test_a_disconnected_session_fires_and_reconnecting_clears() -> None:
    down = FakeSessions([SessionState("s1", "+573001112233", connected=False)])
    up = FakeSessions([SessionState("s1", "+573001112233", connected=True)])
    rule = _rule(RULE_WHATSAPP_SESSION_DOWN)

    fired = await WhatsAppSessionDownEvaluator(down).evaluate(rule)
    cleared = await WhatsAppSessionDownEvaluator(up).evaluate(rule, open_refs=["s1"])

    assert [s.ref for s in fired.firing] == ["s1"]
    # "Conectada" no es un número que oscile en un umbral: es un estado, y reconectar re-arma.
    assert cleared.cleared == ["s1"]
    assert cleared.firing == []


async def test_a_banned_number_counts_as_not_receiving() -> None:
    # Para arreglarlo importa la diferencia; para saber que la sucursal está muda, no.
    banned = FakeSessions([SessionState("s1", "+57300", connected=False)])
    result = await WhatsAppSessionDownEvaluator(banned).evaluate(_rule(RULE_WHATSAPP_SESSION_DOWN))
    assert len(result.firing) == 1


async def test_the_rule_is_inert_without_sessions() -> None:
    """Un negocio que no usa WhatsApp no puede recibir alertas de que su WhatsApp está caído."""
    result = await WhatsAppSessionDownEvaluator(FakeSessions([])).evaluate(
        _rule(RULE_WHATSAPP_SESSION_DOWN)
    )
    assert result.firing == []
    assert result.cleared == []


# --- Caja abierta -----------------------------------------------------------
async def test_cash_left_open_fires_past_the_configured_hour() -> None:
    opened = now_local() - timedelta(hours=6)
    cash = FakeCash(OpenCashSession("c1", opened))
    # Umbral: la hora actual, para que el test valga a cualquier hora del día.
    rule = _rule(RULE_CASH_SESSION_LEFT_OPEN, threshold=now_local().hour, recovery_buffer=1)

    result = await CashSessionLeftOpenEvaluator(cash).evaluate(rule)

    assert [s.ref for s in result.firing] == ["c1"]


async def test_cash_does_not_fire_before_the_hour() -> None:
    cash = FakeCash(OpenCashSession("c1", now_local() - timedelta(hours=1)))
    # Una hora que aún no ha llegado (mañana por la mañana desde cualquier momento).
    rule = _rule(RULE_CASH_SESSION_LEFT_OPEN, threshold=23, recovery_buffer=1)
    result = await CashSessionLeftOpenEvaluator(cash).evaluate(rule)
    if now_local().hour < 23:
        assert result.firing == []


async def test_closing_the_cash_clears_it() -> None:
    result = await CashSessionLeftOpenEvaluator(FakeCash(None)).evaluate(
        _rule(RULE_CASH_SESSION_LEFT_OPEN), open_refs=["c1"]
    )
    assert result.cleared == ["c1"]


async def test_a_cash_just_opened_does_not_fire_in_the_same_minute() -> None:
    """Abrir la caja a las 23:01 no puede disparar mientras alguien la está abriendo."""
    cash = FakeCash(OpenCashSession("c1", now_local()))
    rule = _rule(RULE_CASH_SESSION_LEFT_OPEN, threshold=now_local().hour, recovery_buffer=30)
    result = await CashSessionLeftOpenEvaluator(cash).evaluate(rule)
    assert result.firing == []


# --- El registro ------------------------------------------------------------
def test_a_missing_reader_leaves_its_rule_out() -> None:
    """El módulo tiene que funcionar con WhatsApp completamente ausente."""
    registry = build_registry(inventory=FakeInventory([]), sessions=None, cash=None)
    assert RULE_LOW_STOCK in registry
    assert RULE_WHATSAPP_SESSION_DOWN not in registry


def test_the_registry_is_keyed_so_a_new_rule_needs_no_edit_here() -> None:
    registry = build_registry(
        inventory=FakeInventory([]), sessions=FakeSessions([]), cash=FakeCash(None)
    )
    assert set(registry) == {
        RULE_LOW_STOCK,
        RULE_WHATSAPP_SESSION_DOWN,
        RULE_CASH_SESSION_LEFT_OPEN,
    }


# --- El barrido, contra la base de datos de verdad --------------------------
async def _sweeper(
    branch_id: uuid.UUID, inventory: FakeInventory, channel: RecordingChannel
) -> tuple[AlertSweeper, SqlAlchemyAlertRepository, AlertRule]:
    tenant_id = await demo_tenant_id()
    repo = SqlAlchemyAlertRepository(tracked_session())
    lifecycle = AlertLifecycle(repo, channels=[channel])
    rule = AlertRule(
        tenant_id=tenant_id,
        branch_id=branch_id,
        rule_key=RULE_LOW_STOCK,
        is_enabled=True,
        recovery_buffer=2,
    )
    await repo.save_rule(rule)
    sweeper = AlertSweeper(repo, lifecycle, {RULE_LOW_STOCK: LowStockEvaluator(inventory)})
    return sweeper, repo, rule


async def test_an_oscillating_value_produces_exactly_one_alert(
    branch_id: uuid.UUID,
) -> None:
    """El caso que justifica la histéresis entera.

    El stock baja, sube justo al mínimo, vuelve a bajar — cuatro veces. Sin colchón serían
    cuatro alertas y cuatro avisos, alguien silenciaría el módulo, y la siguiente alerta de
    verdad no la vería nadie.
    """
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=9, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)

    for current in (9, 10, 9, 10, 9):
        inventory.levels = [StockLevel(TOMATO, "Tomate", current=current, minimum=10)]
        await sweeper.evaluate_rule(rule)

    assert len(channel.sent) == 1
    assert len(await repo.list_open(rule.tenant_id, branch_id)) == 1


async def test_the_sweep_is_authoritative_with_the_job_path_gone(
    branch_id: uuid.UUID,
) -> None:
    """Nadie anunció nada. El barrido la encuentra igual — tarde, pero seguro."""
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=1, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)

    result = await sweeper.sweep()

    assert result.fired == 1
    assert len(await repo.list_open(rule.tenant_id, branch_id)) == 1


async def test_the_job_and_the_sweep_racing_produce_one_alert(
    branch_id: uuid.UUID,
) -> None:
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=1, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)

    await sweeper.evaluate_subject(rule.tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    await sweeper.sweep()

    # Lo decide la constraint, no un `if`: los dos caminos pueden mirar el mismo tomate.
    assert len(channel.sent) == 1
    assert len(await repo.list_open(rule.tenant_id, branch_id)) == 1


async def test_recovering_past_the_buffer_closes_the_alert(
    branch_id: uuid.UUID,
) -> None:
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=1, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)
    await sweeper.sweep()

    inventory.levels = [StockLevel(TOMATO, "Tomate", current=15, minimum=10)]
    result = await sweeper.sweep()

    assert result.resolved == 1
    assert await repo.list_open(rule.tenant_id, branch_id) == []


async def test_a_disabled_rule_is_never_evaluated(branch_id: uuid.UUID) -> None:
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=1, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)
    rule.is_enabled = False
    await repo.save_rule(rule)

    result = await sweeper.sweep()

    # Encender una regla es una decisión del dueño. Instalar el módulo no avisa a nadie.
    assert result.fired == 0
    assert channel.sent == []


async def test_a_rule_that_explodes_does_not_take_the_sweep_down(
    branch_id: uuid.UUID,
) -> None:
    class Exploding:
        rule_key = RULE_LOW_STOCK

        async def evaluate(self, rule, subject_ref=None, open_refs=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("la consulta falló")

    tenant_id = await demo_tenant_id()
    repo = SqlAlchemyAlertRepository(tracked_session())
    rule = AlertRule(
        tenant_id=tenant_id,
        branch_id=branch_id,
        rule_key=RULE_LOW_STOCK,
        is_enabled=True,
        recovery_buffer=2,
    )
    await repo.save_rule(rule)
    sweeper = AlertSweeper(
        repo,
        AlertLifecycle(repo),
        {RULE_LOW_STOCK: Exploding()},  # type: ignore[dict-item]
    )

    # Las demás sucursales siguen necesitando sus alertas: una regla rota no se lleva la pasada.
    result = await sweeper.sweep()
    assert result.fired == 0


async def test_the_sweep_sees_every_branch_not_only_the_busy_ones(
    branch_id: uuid.UUID,
) -> None:
    """La sucursal que lleva dos días sin actividad es justo la que hay que mirar."""
    from tests.modules.alerts.conftest import create_branch

    other = await create_branch(f"q{uuid.uuid4().hex[:6]}")
    inventory = FakeInventory([StockLevel(TOMATO, "Tomate", current=1, minimum=10)])
    channel = RecordingChannel()
    sweeper, repo, rule = await _sweeper(branch_id, inventory, channel)
    await repo.save_rule(
        AlertRule(
            tenant_id=rule.tenant_id,
            branch_id=other,
            rule_key=RULE_LOW_STOCK,
            is_enabled=True,
            recovery_buffer=2,
        )
    )

    result = await sweeper.sweep()

    assert result.fired == 2
    assert len(await repo.list_open(rule.tenant_id, other)) == 1


async def test_a_utc_naive_open_time_is_read_as_utc() -> None:
    """SQLite devuelve el instante sin zona; restarlo del local reventaría."""
    naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=3)
    cash = FakeCash(OpenCashSession("c1", naive))
    rule = _rule(RULE_CASH_SESSION_LEFT_OPEN, threshold=now_local().hour, recovery_buffer=1)

    result = await CashSessionLeftOpenEvaluator(cash).evaluate(rule)

    assert [s.ref for s in result.firing] == ["c1"]
