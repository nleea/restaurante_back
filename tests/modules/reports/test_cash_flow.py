"""Cash-flow tests: money-in/out assembly, categories, cash-vs-other split, de-dup."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from httpx import AsyncClient

from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.domain.ports import MoneyFlowRow, MovementFlowRow
from tests.modules.staff.test_staff_api import _assign_role, _create_branch, _login

_FROM = dt.date(2025, 1, 1)
_TO = dt.date(2025, 1, 31)
_D1 = "2025-01-05"
_D2 = "2025-01-06"


class _FakeRepo:
    def __init__(
        self,
        *,
        sales: list[MoneyFlowRow] | None = None,
        supplier: list[MoneyFlowRow] | None = None,
        expenses: list[tuple[str, Decimal]] | None = None,
        mov_in: list[MovementFlowRow] | None = None,
        mov_out: list[MovementFlowRow] | None = None,
    ) -> None:
        self._sales = sales or []
        self._supplier = supplier or []
        self._expenses = expenses or []
        self._mov_in = mov_in or []
        self._mov_out = mov_out or []

    async def cf_sales(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._sales

    async def cf_supplier_payments(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._supplier

    async def cf_expenses(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._expenses

    async def cf_movements(self, tenant_id, branch_id, date_from, date_to, direction):  # noqa: ANN001, ANN201
        return self._mov_in if direction == "in" else self._mov_out


def _svc(**kwargs: object) -> ReportsService:
    return ReportsService(_FakeRepo(**kwargs))  # type: ignore[arg-type]


async def _run(**kwargs: object):  # noqa: ANN202
    return await _svc(**kwargs).cash_flow(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)


async def test_cash_flow_categories_split_and_net() -> None:
    cf = await _run(
        sales=[
            MoneyFlowRow("cash", _D1, Decimal("100000")),
            MoneyFlowRow("card", _D1, Decimal("50000")),
        ],
        supplier=[MoneyFlowRow("transfer", _D1, Decimal("40000"))],
        expenses=[(_D1, Decimal("30000"))],
        mov_in=[
            MovementFlowRow("credit_payment", "cash", _D1, Decimal("20000")),
            MovementFlowRow("adjustment", "cash", _D1, Decimal("10000")),
        ],
        mov_out=[MovementFlowRow("withdrawal", "cash", _D1, Decimal("25000"))],
    )

    assert cf.inflows == Decimal("180000")  # 100 + 50 + 20 + 10
    assert cf.outflows == Decimal("95000")  # 40 + 30 + 25
    assert cf.net == Decimal("85000")
    # cash vs other
    assert cf.cash_inflows == Decimal("130000")  # 100 + 20 + 10
    assert cf.other_inflows == Decimal("50000")  # card
    assert cf.cash_outflows == Decimal("25000")  # retiro
    assert cf.other_outflows == Decimal("70000")  # supplier transfer 40 + expenses 30

    cats = {(c.category, c.direction): c.amount for c in cf.categories}
    assert cats[("Ventas", "in")] == Decimal("150000")
    assert cats[("Abonos a crédito", "in")] == Decimal("20000")
    assert cats[("Ingresos de caja", "in")] == Decimal("10000")
    assert cats[("Compras", "out")] == Decimal("40000")
    assert cats[("Gastos", "out")] == Decimal("30000")
    assert cats[("Retiros de caja", "out")] == Decimal("25000")


async def test_purchase_payment_is_an_outflow() -> None:
    # The whole point: a paid purchase of insumos is visible as money-out.
    cf = await _run(supplier=[MoneyFlowRow("cash", _D1, Decimal("75000"))])
    assert cf.outflows == Decimal("75000")
    assert cf.cash_outflows == Decimal("75000")
    cats = {(c.category, c.direction): c.amount for c in cf.categories}
    assert cats[("Compras", "out")] == Decimal("75000")


async def test_expenses_classified_as_other_not_cash() -> None:
    cf = await _run(expenses=[(_D1, Decimal("12000"))])
    assert cf.cash_outflows == Decimal("0")
    assert cf.other_outflows == Decimal("12000")


async def test_sales_counted_once_dedup_contract() -> None:
    # The repo excludes `sale` movements from cf_movements("in"); the service reads
    # the sale only from cf_sales. Feeding a manual-only mov_in proves no re-add.
    cf = await _run(
        sales=[MoneyFlowRow("cash", _D1, Decimal("90000"))],
        mov_in=[MovementFlowRow("adjustment", "cash", _D1, Decimal("5000"))],
    )
    assert cf.inflows == Decimal("95000")  # 90 sale + 5 manual, sale not doubled


async def test_daily_series_spans_multiple_days() -> None:
    cf = await _run(
        sales=[MoneyFlowRow("cash", _D1, Decimal("60000"))],
        expenses=[(_D2, Decimal("20000"))],
    )
    by_day = {d.day: d for d in cf.daily}
    assert by_day[_D1].inflow == Decimal("60000")
    assert by_day[_D1].net == Decimal("60000")
    assert by_day[_D2].outflow == Decimal("20000")
    assert by_day[_D2].net == Decimal("-20000")


async def test_cash_flow_endpoint_empty_and_scoped(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/reports/cash-flow",
        headers=headers,
        params={"branch_id": str(branch_id), "from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["inflows"]) == Decimal("0")
    assert Decimal(body["outflows"]) == Decimal("0")
    assert Decimal(body["net"]) == Decimal("0")
    assert body["categories"] == []
    assert body["daily"] == []


async def test_cash_flow_requires_permission(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get(
        "/reports/cash-flow",
        headers=headers,
        params={"branch_id": str(uuid.uuid4()), "from": "2025-01-01", "to": "2025-01-31"},
    )
    assert resp.status_code == 403
