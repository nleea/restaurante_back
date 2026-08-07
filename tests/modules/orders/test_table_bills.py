"""La cuenta de mesa: agrupar, cobrar en cascada y cerrar en bloque.

Lo que se protege aquí es que nunca quede una comanda cerrada sin cubrir ni cobrada dos veces.
Un fallo así no se ve al hacerlo: aparece en el arqueo del turno, cuando ya nadie recuerda qué
mesa fue.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from restaurante.modules.cash.infrastructure.models import CashMovementModel
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.domain.bill_allocation import BillPayment
from restaurante.modules.orders.infrastructure.models import (
    DiningTableModel,
    OrderModel,
    OrderPaymentModel,
    TableBillModel,
)
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ConflictError, ValidationError
from tests.modules._cash import seed_open_cash_session
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_variant,
    _demo_ids,
    _login,
)


class Scenario:
    """Una mesa con N comandas abiertas, cada una con su total."""

    def __init__(self, tenant_id, branch_id, employee_id, table_id, order_ids):
        self.tenant_id = tenant_id
        self.branch_id = branch_id
        self.employee_id = employee_id
        self.table_id = table_id
        self.order_ids = order_ids


async def _seed(client: AsyncClient, amounts: list[str]) -> Scenario:
    """Crea una mesa con una comanda por importe, cada una con un ítem de ese precio."""
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    # Código único por escenario: dos llamadas seguidas chocarían con la unicidad de sede.
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    employee_id = await _create_employee(branch_id, email=f'w{uuid.uuid4().hex[:8]}@demo.com')
    await seed_open_cash_session(branch_id, employee_id)
    variant_id = await _create_variant()

    table = await client.post(
        "/orders/tables",
        headers=headers,
        json={"branch_id": str(branch_id), "number": "5", "capacity": 6},
    )
    table_id = uuid.UUID(table.json()["id"])

    order_ids = []
    for amount in amounts:
        resp = await client.post(
            "/orders",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "channel": "dine_in",
                "employee_id": str(employee_id),
                "dining_table_id": str(table_id),
            },
        )
        order_id = resp.json()["id"]
        await client.post(
            f"/orders/{order_id}/items",
            headers=headers,
            json={
                "product_variant_id": str(variant_id),
                "quantity": 1,
                "unit_price": amount,
            },
        )
        order_ids.append(uuid.UUID(order_id))
    return Scenario(tenant_id, branch_id, employee_id, table_id, order_ids)


def _service(session) -> OrderService:
    return OrderService(repo=SqlAlchemyOrdersRepository(session))


async def _count(model, **where) -> int:
    async with SessionFactory() as session:
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return int((await session.execute(stmt)).scalar_one())


async def _order_statuses(order_ids: list[uuid.UUID]) -> list[str]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(OrderModel.status).where(OrderModel.id.in_(order_ids))
            )
        ).scalars()
        return sorted(rows)


async def _table_status(table_id: uuid.UUID) -> str:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(DiningTableModel.status).where(DiningTableModel.id == table_id)
            )
        ).scalar_one()


# --- Agrupar ------------------------------------------------------------------
async def test_opening_a_bill_takes_every_open_order_of_the_table(
    client: AsyncClient,
) -> None:
    """Todo junto es el caso común: casi todas las mesas pagan juntas."""
    s = await _seed(client, ["32000", "54000", "34000"])

    async with SessionFactory() as session:
        bill, members = await _service(session).open_table_bill(
            s.tenant_id, s.table_id, s.employee_id
        )

    assert len(members) == 3
    assert bill.status == "open"
    # La cuenta NO congela importe al abrir: un comensal puede pedir un café todavía.
    assert bill.total == 0


async def test_a_bill_of_one_is_the_same_mechanism(client: AsyncClient) -> None:
    """Separar no es otro camino: es esta misma cuenta con menos miembros."""
    s = await _seed(client, ["32000", "54000"])

    async with SessionFactory() as session:
        _, members = await _service(session).open_table_bill(
            s.tenant_id, s.table_id, s.employee_id, order_ids=[s.order_ids[1]]
        )

    assert [m.id for m in members] == [s.order_ids[1]]
    # La otra comanda queda intacta y sin cuenta.
    assert await _count(OrderModel, table_bill_id=None) >= 1


async def test_an_order_already_on_a_bill_is_refused(client: AsyncClient) -> None:
    s = await _seed(client, ["32000", "54000"])

    async with SessionFactory() as session:
        await _service(session).open_table_bill(s.tenant_id, s.table_id, s.employee_id)

    async with SessionFactory() as session:
        with pytest.raises(ConflictError):
            await _service(session).open_table_bill(
                s.tenant_id, s.table_id, s.employee_id, order_ids=[s.order_ids[0]]
            )
    # Y la cuenta fallida no deja rastro: el `unit_of_work` deshizo su propia fila.
    assert await _count(TableBillModel) == 1


async def test_an_order_from_another_table_is_refused(client: AsyncClient) -> None:
    s = await _seed(client, ["32000"])
    other = await _seed(client, ["10000"])

    async with SessionFactory() as session:
        with pytest.raises(ValidationError):
            await _service(session).open_table_bill(
                s.tenant_id, s.table_id, s.employee_id, order_ids=[other.order_ids[0]]
            )
    assert await _count(TableBillModel) == 0


async def test_dissolving_releases_the_members_untouched(client: AsyncClient) -> None:
    s = await _seed(client, ["32000", "54000"])

    async with SessionFactory() as session:
        bill, _ = await _service(session).open_table_bill(
            s.tenant_id, s.table_id, s.employee_id
        )
    async with SessionFactory() as session:
        await _service(session).dissolve_table_bill(s.tenant_id, bill.id)

    assert await _count(TableBillModel) == 0
    assert await _order_statuses(s.order_ids) == ["open", "open"]
    assert await _count(OrderPaymentModel) == 0


# --- Cobrar -------------------------------------------------------------------
async def test_one_payment_covers_closes_and_settles(client: AsyncClient) -> None:
    """El gesto completo: un billete, tres comandas cerradas y la cuenta liquidada."""
    s = await _seed(client, ["32000", "54000", "34000"])

    async with SessionFactory() as session:
        service = _service(session)
        bill, _ = await service.open_table_bill(
            s.tenant_id, s.table_id, s.employee_id
        )
        settled, uncovered = await service.charge_table_bill(
            s.tenant_id, bill.id, [BillPayment(Decimal("120000"), "cash")], s.employee_id
        )

    assert uncovered == 0
    assert settled.status == "settled"
    assert settled.total == Decimal("120000.00")
    assert await _order_statuses(s.order_ids) == ["closed", "closed", "closed"]
    # Un pago real por comanda: `order_payments` sigue siendo la única verdad de "pagado".
    assert await _count(OrderPaymentModel) == 3
    # Y su movimiento de caja: para el arqueo es la misma plata.
    assert await _count(CashMovementModel, category="sale") == 3


async def test_two_methods_straddle_one_order(client: AsyncClient) -> None:
    """Exactamente UNA comanda queda a caballo de los dos métodos.

    No se afirma CUÁL: el orden del reparto es `created_at` y, cuando empata, el `id` — estable
    dentro de una ejecución pero no predecible desde aquí. Lo que sí es una propiedad del
    sistema es la forma: la cascada parte un solo pago, la prorrata habría partido los tres.
    """
    s = await _seed(client, ["32000", "54000", "34000"])

    async with SessionFactory() as session:
        service = _service(session)
        bill, _ = await service.open_table_bill(s.tenant_id, s.table_id, s.employee_id)
        _, uncovered = await service.charge_table_bill(
            s.tenant_id,
            bill.id,
            [BillPayment(Decimal("80000"), "card"), BillPayment(Decimal("40000"), "cash")],
            s.employee_id,
        )

    assert uncovered == 0
    counts = [await _count(OrderPaymentModel, order_id=oid) for oid in s.order_ids]
    assert sorted(counts) == [1, 1, 2]  # dos enteras + una partida
    assert await _order_statuses(s.order_ids) == ["closed", "closed", "closed"]


async def test_a_partial_charge_closes_nothing(client: AsyncClient) -> None:
    """Cobrar de menos es legítimo —el cajero recibe lo que le den— pero no cierra nada."""
    s = await _seed(client, ["32000", "54000"])

    async with SessionFactory() as session:
        service = _service(session)
        bill, _ = await service.open_table_bill(s.tenant_id, s.table_id, s.employee_id)
        updated, uncovered = await service.charge_table_bill(
            s.tenant_id, bill.id, [BillPayment(Decimal("40000"), "cash")], s.employee_id
        )

    assert uncovered == Decimal("46000.00")
    assert updated.status == "open"
    assert await _order_statuses(s.order_ids) == ["open", "open"]


async def test_the_table_is_freed_only_when_the_bill_took_the_last_orders(
    client: AsyncClient,
) -> None:
    s = await _seed(client, ["32000", "54000"])

    async with SessionFactory() as session:
        service = _service(session)
        # Cuenta de UNO: la otra comanda sigue viva en la mesa.
        bill, _ = await service.open_table_bill(
            s.tenant_id, s.table_id, s.employee_id, order_ids=[s.order_ids[0]]
        )
        await service.charge_table_bill(
            s.tenant_id, bill.id, [BillPayment(Decimal("32000"), "cash")], s.employee_id
        )
    assert await _table_status(s.table_id) == "occupied"

    async with SessionFactory() as session:
        service = _service(session)
        bill2, _ = await service.open_table_bill(
            s.tenant_id, s.table_id, s.employee_id, order_ids=[s.order_ids[1]]
        )
        await service.charge_table_bill(
            s.tenant_id, bill2.id, [BillPayment(Decimal("54000"), "cash")], s.employee_id
        )
    assert await _table_status(s.table_id) == "free"


async def test_no_open_cash_session_writes_nothing(client: AsyncClient) -> None:
    s = await _seed(client, ["32000"])
    async with SessionFactory() as session:
        bill, _ = await _service(session).open_table_bill(
            s.tenant_id, s.table_id, s.employee_id
        )
    # Cierra la caja del turno.
    async with SessionFactory() as session:
        from restaurante.modules.cash.infrastructure.models import CashSessionModel

        await session.execute(
            CashSessionModel.__table__.update()
            .where(CashSessionModel.branch_id == s.branch_id)
            .values(status="closed")
        )
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(ConflictError):
            await _service(session).charge_table_bill(
                s.tenant_id, bill.id, [BillPayment(Decimal("32000"), "cash")], s.employee_id
            )

    assert await _count(OrderPaymentModel) == 0
    assert await _count(CashMovementModel, category="sale") == 0


async def test_a_failure_halfway_leaves_nothing_behind(client: AsyncClient) -> None:
    """El test que justifica toda la unidad de trabajo.

    Se fuerza un fallo DESPUÉS de haber cubierto la primera comanda. Sin transacción única,
    Ana quedaría cobrada y cerrada mientras el resto de la mesa sigue abierta: dinero registrado
    contra un cierre que nunca ocurrió, y nadie mirando.
    """
    s = await _seed(client, ["32000", "54000", "34000"])

    async with SessionFactory() as session:
        service = _service(session)
        bill, _ = await service.open_table_bill(s.tenant_id, s.table_id, s.employee_id)

    async with SessionFactory() as session:
        service = _service(session)
        calls = {"n": 0}
        real_close = service.close_order

        async def exploding_close(tenant_id, order_id, **kw):
            calls["n"] += 1
            if calls["n"] == 2:  # ya cerró la primera; revienta en la segunda
                raise RuntimeError("la base se cayó a mitad del cobro")
            return await real_close(tenant_id, order_id, **kw)

        service.close_order = exploding_close  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await service.charge_table_bill(
                s.tenant_id,
                bill.id,
                [BillPayment(Decimal("120000"), "cash")],
                s.employee_id,
            )

    # NADA sobrevive: ni un pago, ni un movimiento, ni un cierre.
    assert await _count(OrderPaymentModel) == 0
    assert await _count(CashMovementModel, category="sale") == 0
    assert await _order_statuses(s.order_ids) == ["open", "open", "open"]


async def test_a_settled_bill_cannot_be_charged_again(client: AsyncClient) -> None:
    s = await _seed(client, ["32000"])

    async with SessionFactory() as session:
        service = _service(session)
        bill, _ = await service.open_table_bill(s.tenant_id, s.table_id, s.employee_id)
        await service.charge_table_bill(
            s.tenant_id, bill.id, [BillPayment(Decimal("32000"), "cash")], s.employee_id
        )

    async with SessionFactory() as session:
        with pytest.raises(ConflictError):
            await _service(session).charge_table_bill(
                s.tenant_id, bill.id, [BillPayment(Decimal("1000"), "cash")], s.employee_id
            )
    assert await _count(OrderPaymentModel) == 1
