"""Product-costing (COGS) tests: the BOM rollup logic + endpoint wiring."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from httpx import AsyncClient

from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.domain.ports import RecipeItemRow, SoldItemRow
from tests.modules.staff.test_staff_api import _assign_role, _create_branch, _login


class _FakeRepo:
    """Only the three methods `cogs_summary` calls; the rest are unused here."""

    def __init__(
        self,
        costs: list[tuple[uuid.UUID, Decimal]],
        recipe: list[RecipeItemRow],
        sold: list[SoldItemRow],
    ) -> None:
        self._costs = costs
        self._recipe = recipe
        self._sold = sold

    async def ingredient_avg_costs(self, tenant_id: uuid.UUID):  # noqa: ANN201
        return self._costs

    async def all_recipe_items(self, tenant_id: uuid.UUID):  # noqa: ANN201
        return self._recipe

    async def sold_items_by_channel(self, tenant_id, branch_id, date_from, date_to):  # noqa: ANN201
        return self._sold


async def test_cogs_rollup_and_partial_flag() -> None:
    ing_a, ing_b, missing = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    var1, var2 = uuid.uuid4(), uuid.uuid4()
    costs = [(ing_a, Decimal("1000")), (ing_b, Decimal("500"))]
    recipe = [
        RecipeItemRow(var1, ing_a, Decimal("2")),  # 2 × 1000
        RecipeItemRow(var1, ing_b, Decimal("1")),  # 1 × 500  → var1 cost 2500
        RecipeItemRow(var2, ing_a, Decimal("1")),  # 1 × 1000
        RecipeItemRow(var2, missing, Decimal("3")),  # missing cost → var2 partial
    ]
    sold = [
        SoldItemRow("dine_in", var1, 3),  # 3 × 2500 = 7500
        SoldItemRow("delivery", var2, 2),  # 2 × 1000 = 2000 (priced part only)
    ]
    service = ReportsService(_FakeRepo(costs, recipe, sold))  # type: ignore[arg-type]

    result = await service.cogs_summary(
        uuid.uuid4(), uuid.uuid4(), dt.date(2025, 1, 1), dt.date(2025, 1, 31)
    )

    assert result.cogs == Decimal("9500")
    assert result.partial is True  # var2 has an unpriced ingredient
    assert result.priced_variants == 1
    assert result.unpriced_variants == 1
    channels = {c.channel: c.cogs for c in result.channels}
    assert channels["dine_in"] == Decimal("7500")
    assert channels["delivery"] == Decimal("2000")


async def test_cogs_endpoint_empty_and_scoped(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/reports/cogs",
        headers=headers,
        params={"branch_id": str(branch_id), "from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["cogs"]) == Decimal("0")
    assert body["partial"] is False
    assert body["channels"] == []


async def test_cogs_requires_permission(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get(
        "/reports/cogs",
        headers=headers,
        params={"branch_id": str(uuid.uuid4()), "from": "2025-01-01", "to": "2025-01-31"},
    )
    assert resp.status_code == 403
