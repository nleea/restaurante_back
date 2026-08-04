"""Branch-addressed public storefront: `/storefront/<branch-code>/...`.

The load-bearing behaviour here is the NEGATIVE one: an unknown or inactive branch code
must 404 and must never fall back to the primary branch. A 404 is recoverable; an order
placed in Centro that prints in Norte is not.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.domain.entities import OperatingHours
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ValidationError
from restaurante.shared.tenancy.branch_code import (
    is_valid_branch_code,
    validate_branch_code,
)
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_branch_price,
    seed_menu,
    seed_primary_branch,
)


def _pickup_payload(seeded: SeededMenu) -> dict[str, Any]:
    return {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [{"variantId": str(seeded.variant_id), "quantity": 1}],
    }


# --- menu ------------------------------------------------------------------


async def test_menu_resolves_the_addressed_branch(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)

    resp = await client.get("/storefront/centro/menu")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["name"] for p in body["products"]] == ["Ceviche Mixto"]
    assert body["products"][0]["variantId"] == str(seeded.variant_id)


async def test_two_branches_return_their_own_prices(client: AsyncClient) -> None:
    """Products are tenant-level; only the PRICE is per branch — so price is the tell."""
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)
    seeded = await seed_menu(centro, price="28000.00")
    await seed_branch_price(norte, seeded.product_id, "31000.00")

    centro_body = (await client.get("/storefront/centro/menu")).json()
    norte_body = (await client.get("/storefront/norte/menu")).json()

    def price_of(body: dict[str, Any]) -> str:
        return next(
            p["price"] for p in body["products"] if p["id"] == str(seeded.product_id)
        )

    assert price_of(centro_body) == "28000.00"
    assert price_of(norte_body) == "31000.00"


async def test_codeless_menu_still_resolves_the_primary_branch(
    client: AsyncClient,
) -> None:
    """Regression: single-branch tenants keep the short link."""
    primary = await seed_primary_branch(code="centro")
    await seed_primary_branch(code="norte", is_primary=False)
    await seed_menu(primary, price="28000.00")

    body = (await client.get("/storefront/menu")).json()
    assert [p["price"] for p in body["products"]] == ["28000.00"]


# --- unknown / inactive codes ----------------------------------------------


async def test_unknown_branch_code_is_404(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    await seed_menu(branch_id)

    resp = await client.get("/storefront/no-existe/menu")
    assert resp.status_code == 404
    assert resp.json()["code"] == "branch_not_found"


async def test_inactive_branch_code_is_404(client: AsyncClient) -> None:
    await seed_primary_branch(code="centro")
    await seed_primary_branch(code="cerrada", is_primary=False, is_active=False)

    resp = await client.get("/storefront/cerrada/menu")
    assert resp.status_code == 404
    assert resp.json()["code"] == "branch_not_found"


async def test_unknown_code_creates_no_order_anywhere(client: AsyncClient) -> None:
    """The dangerous failure would be silently ordering from the primary branch."""
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post(
        "/storefront/no-existe/orders", json=_pickup_payload(seeded)
    )
    assert resp.status_code == 404

    async with SessionFactory() as session:
        orders = (await session.execute(select(OrderModel))).scalars().all()
    assert orders == []


# --- order intake ----------------------------------------------------------


async def test_order_lands_on_the_addressed_branch(client: AsyncClient) -> None:
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)
    seeded = await seed_menu(norte)
    await seed_open_cash_session(norte)

    resp = await client.post("/storefront/norte/orders", json=_pickup_payload(seeded))
    assert resp.status_code == 201, resp.text

    order_id = uuid.UUID(resp.json()["orderId"])
    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
    assert order.branch_id == norte
    assert order.branch_id != centro


async def test_body_cannot_override_the_addressed_branch(client: AsyncClient) -> None:
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)
    seeded = await seed_menu(norte)
    await seed_open_cash_session(norte)

    payload = _pickup_payload(seeded)
    payload["branchId"] = str(centro)  # ignored: the branch comes from the path
    payload["branch_code"] = "centro"

    resp = await client.post("/storefront/norte/orders", json=payload)
    assert resp.status_code == 201, resp.text

    order_id = uuid.UUID(resp.json()["orderId"])
    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
    assert order.branch_id == norte


async def test_caja_gate_applies_to_the_addressed_branch(client: AsyncClient) -> None:
    """Another branch having an open caja must not let this one take orders."""
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)
    seeded = await seed_menu(norte)
    await seed_open_cash_session(centro)  # open on the OTHER branch only

    resp = await client.post("/storefront/norte/orders", json=_pickup_payload(seeded))
    assert resp.status_code == 409
    assert resp.json()["code"] == "cash_closed"

    async with SessionFactory() as session:
        orders = (await session.execute(select(OrderModel))).scalars().all()
    assert orders == []


# --- hours -----------------------------------------------------------------


async def test_hours_belong_to_the_addressed_branch(client: AsyncClient) -> None:
    """A closed sede reports ITS own state, even when a sibling branch is open."""
    tenant_id = await demo_tenant_id()
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)

    today = datetime.now().weekday()
    async with SessionFactory() as session:
        svc = BusinessService(repo=SqlAlchemyBusinessRepository(session))
        # Centro open all day today; Norte has no window today at all.
        await svc.set_hours(
            tenant_id,
            centro,
            [
                OperatingHours(
                    tenant_id=tenant_id,
                    branch_id=centro,
                    weekday=today,
                    open_minute=0,
                    close_minute=24 * 60 - 1,
                )
            ],
        )
        await svc.set_hours(
            tenant_id,
            norte,
            [
                OperatingHours(
                    tenant_id=tenant_id,
                    branch_id=norte,
                    weekday=(today + 1) % 7,
                    open_minute=10 * 60,
                    close_minute=20 * 60,
                )
            ],
        )

    assert (await client.get("/storefront/centro/hours")).json()["isOpenNow"] is True

    norte_body = (await client.get("/storefront/norte/hours")).json()
    assert norte_body["isOpenNow"] is False
    assert norte_body["nextOpening"] == {"weekday": (today + 1) % 7, "minute": 600}


async def test_hours_unknown_branch_is_404(client: AsyncClient) -> None:
    await seed_primary_branch(code="centro")
    resp = await client.get("/storefront/no-existe/hours")
    assert resp.status_code == 404


# --- branch listing --------------------------------------------------------


async def test_branches_lists_active_only(client: AsyncClient) -> None:
    await seed_primary_branch(code="centro")
    await seed_primary_branch(code="norte", is_primary=False)
    await seed_primary_branch(code="cerrada", is_primary=False, is_active=False)

    resp = await client.get("/storefront/branches")
    assert resp.status_code == 200
    codes = [b["code"] for b in resp.json()]
    assert codes == ["centro", "norte"]  # primary first, then by name
    assert all("isActive" not in b for b in resp.json())


# --- branch code format ----------------------------------------------------


@pytest.mark.parametrize("code", ["centro", "b1", "centro-norte", "sede-2", "x"])
def test_slug_form_codes_are_accepted(code: str) -> None:
    assert is_valid_branch_code(code)
    assert validate_branch_code(code) == code


@pytest.mark.parametrize(
    "code",
    [
        "Sede #1 (Centro)",
        "MAIN",
        "con espacio",
        "-centro",
        "centro-",
        "centro--norte",
        "acentuación",
        "",
        "x" * 33,
    ],
)
def test_non_slug_codes_are_rejected(code: str) -> None:
    assert not is_valid_branch_code(code)
    with pytest.raises(ValidationError):
        validate_branch_code(code)
