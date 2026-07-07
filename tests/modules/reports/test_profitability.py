"""Profitability tests: P&L math, margin-by-channel, cost KPIs, product margins."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from httpx import AsyncClient

from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.domain.ports import (
    ChannelAgg,
    RecipeItemRow,
    SoldItemRow,
    VariantSalesRow,
)
from tests.modules.staff.test_staff_api import _assign_role, _create_branch, _login

_FROM = dt.date(2025, 1, 1)
_TO = dt.date(2025, 1, 31)


class _FakeRepo:
    """A configurable stand-in for the reporting repository.

    Defaults describe one fully-priced product (var1 = 2 × ing_a@1000 → cost
    2000) sold 3× dine_in for 20000 revenue, so downstream math is easy to check.
    """

    def __init__(
        self,
        *,
        channels: list[ChannelAgg] | None = None,
        discounts_returns: tuple[Decimal, Decimal, int] = (
            Decimal(0),
            Decimal(0),
            0,
        ),
        costs: list[tuple[uuid.UUID, Decimal]] | None = None,
        recipe: list[RecipeItemRow] | None = None,
        sold: list[SoldItemRow] | None = None,
        sales: list[VariantSalesRow] | None = None,
        opex: Decimal = Decimal(0),
        labor: Decimal | None = None,
        names: dict[uuid.UUID, str] | None = None,
    ) -> None:
        self.var1 = uuid.uuid4()
        self.ing_a = uuid.uuid4()
        self._channels = (
            channels
            if channels is not None
            else [ChannelAgg("dine_in", Decimal("20000"), 3)]
        )
        self._discounts_returns = discounts_returns
        self._costs = costs if costs is not None else [(self.ing_a, Decimal("1000"))]
        self._recipe = (
            recipe
            if recipe is not None
            else [RecipeItemRow(self.var1, self.ing_a, Decimal("2"))]
        )
        self._sold = (
            sold if sold is not None else [SoldItemRow("dine_in", self.var1, 3)]
        )
        self._sales = (
            sales
            if sales is not None
            else [VariantSalesRow(self.var1, 3, Decimal("20000"))]
        )
        self._opex = opex
        self._labor = labor
        self._names = names or {}

    # revenue_summary
    async def revenue_channels(  # noqa: ANN201
        self, tenant_id, branch_id, date_from, date_to, cashier_employee_id=None  # noqa: ANN001
    ):
        return self._channels

    async def revenue_payments(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return []

    async def revenue_discounts_returns(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._discounts_returns

    # cogs_summary
    async def ingredient_avg_costs(self, tenant_id):  # noqa: ANN001, ANN201
        return self._costs

    async def all_recipe_items(self, tenant_id):  # noqa: ANN001, ANN201
        return self._recipe

    async def sold_items_by_channel(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._sold

    # profitability
    async def expenses_total(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._opex

    async def labor_expenses_total(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._labor

    async def variant_sales(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN001, ANN201
        return self._sales

    async def variant_name(self, tenant_id, variant_id):  # noqa: ANN001, ANN201
        return self._names.get(variant_id)


def _service(**kwargs: object) -> tuple[ReportsService, _FakeRepo]:
    repo = _FakeRepo(**kwargs)  # type: ignore[arg-type]
    return ReportsService(repo), repo  # type: ignore[arg-type]


async def test_pl_math() -> None:
    service, _ = _service(opex=Decimal("5000"))

    pl = await service.profit_and_loss(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)

    assert pl.revenue == Decimal("20000")
    assert pl.cogs == Decimal("6000")  # 3 × (2 × 1000)
    assert pl.cogs_partial is False
    assert pl.gross_profit == Decimal("14000")
    assert pl.gross_margin_pct == Decimal("70.00")
    assert pl.operating_expenses == Decimal("5000")
    assert pl.ebitda == Decimal("9000")
    assert pl.estimated_taxes == Decimal("3193")  # 20000 × 0.19/1.19
    assert pl.net_profit == Decimal("5807")
    assert pl.contribution_margin_pct == Decimal("70.00")
    # break-even = opex × revenue / gross_profit = 5000 × 20000 / 14000
    assert pl.break_even_revenue == Decimal("7143")


async def test_pl_margin_by_channel() -> None:
    service, repo = _service()
    pl = await service.profit_and_loss(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)

    assert len(pl.channels) == 1
    ch = pl.channels[0]
    assert ch.channel == "dine_in"
    assert ch.revenue == Decimal("20000")
    assert ch.cogs == Decimal("6000")
    assert ch.margin == Decimal("14000")
    assert ch.margin_pct == Decimal("70.00")


async def test_pl_break_even_undefined_when_no_contribution() -> None:
    # COGS above revenue → gross profit negative → break-even undefined.
    service, _ = _service(
        sold=[SoldItemRow("dine_in", uuid.UUID(int=1), 1)],  # unknown variant
        channels=[ChannelAgg("dine_in", Decimal("100"), 1)],
        costs=[(uuid.UUID(int=9), Decimal("1"))],
        recipe=[RecipeItemRow(uuid.UUID(int=1), uuid.UUID(int=9), Decimal("500"))],
    )
    pl = await service.profit_and_loss(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)
    assert pl.gross_profit < 0
    assert pl.break_even_revenue is None


async def test_cost_kpis_with_labor() -> None:
    service, _ = _service(labor=Decimal("4000"))
    kpis = await service.cost_kpis(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)

    assert kpis.food_cost_pct == Decimal("30.00")  # 6000 / 20000
    assert kpis.labor_available is True
    assert kpis.labor_cost == Decimal("4000")
    assert kpis.labor_cost_pct == Decimal("20.00")
    assert kpis.prime_cost == Decimal("10000")  # 6000 + 4000
    assert kpis.prime_cost_pct == Decimal("50.00")


async def test_cost_kpis_without_labor_marks_unavailable() -> None:
    service, _ = _service(labor=None)
    kpis = await service.cost_kpis(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)

    assert kpis.food_cost_pct == Decimal("30.00")
    assert kpis.labor_available is False
    assert kpis.labor_cost is None
    assert kpis.labor_cost_pct is None
    assert kpis.prime_cost is None
    assert kpis.prime_cost_pct is None


async def test_product_margins_ranks_priced_and_skips_unpriced() -> None:
    priced = uuid.uuid4()
    unpriced = uuid.uuid4()
    ing = uuid.uuid4()
    missing = uuid.uuid4()
    service, _ = _service(
        costs=[(ing, Decimal("1000"))],
        recipe=[
            RecipeItemRow(priced, ing, Decimal("2")),  # cost 2000
            RecipeItemRow(unpriced, missing, Decimal("1")),  # no cost → partial
        ],
        sales=[
            VariantSalesRow(priced, 3, Decimal("20000")),  # cogs 6000, margin 14000
            VariantSalesRow(unpriced, 2, Decimal("5000")),
        ],
        names={priced: "Hamburguesa", unpriced: "Especial"},
    )

    report = await service.product_margins(uuid.uuid4(), uuid.uuid4(), _FROM, _TO)

    top_ids = {p.variant_id for p in report.top}
    assert priced in top_ids
    assert unpriced not in top_ids  # no cost → excluded from margin ranking
    top = next(p for p in report.top if p.variant_id == priced)
    assert top.name == "Hamburguesa"
    assert top.cogs == Decimal("6000")
    assert top.margin == Decimal("14000")
    assert top.margin_pct == Decimal("70.00")
    assert top.cost_available is True


async def test_pl_endpoint_empty_and_scoped(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/reports/pl",
        headers=headers,
        params={"branch_id": str(branch_id), "from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["revenue"]) == Decimal("0")
    assert Decimal(body["cogs"]) == Decimal("0")
    assert Decimal(body["net_profit"]) == Decimal("0")
    assert body["break_even_revenue"] is None
    assert body["taxes_estimated"] is True
    assert body["channels"] == []


async def test_cost_kpis_endpoint_scoped(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/reports/cost-kpis",
        headers=headers,
        params={"branch_id": str(branch_id), "from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # No labor category seeded → labor cost unavailable.
    assert body["labor_available"] is False
    assert body["labor_cost"] is None


async def test_profitability_requires_permission(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    for path in ("/reports/pl", "/reports/cost-kpis", "/reports/product-margins"):
        resp = await client.get(
            path,
            headers=headers,
            params={
                "branch_id": str(uuid.uuid4()),
                "from": "2025-01-01",
                "to": "2025-01-31",
            },
        )
        assert resp.status_code == 403, path
