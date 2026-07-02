"""Integration tests for kitchen station roles (A) and the order ready rollup (B).

Covers tasks 2.5 and 4.8: role captured per ticket and frozen at routing time; kitchen_state
derivation over an order's tickets; readiness pushed to orders on last-ready; add-item reopening a
ready order; delivery orders auto-creating their dispatch record (idempotent, non-blocking).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.kitchen.application.use_cases.manage_kitchen import (
    KitchenService,
    derive_kitchen_state,
)
from restaurante.modules.kitchen.infrastructure.models import ProductStationModel
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


# --- shared helpers ---------------------------------------------------------
async def _demo_ids() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == TEST_EMAIL)
            )
        ).scalar_one()
        return tenant.id, user.id


async def _assign_admin() -> None:
    from restaurante.modules.identity.infrastructure.repositories import (
        SqlAlchemyRbacRepository,
    )

    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_branch() -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def _create_product_and_variant() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        category = CategoryModel(tenant_id=tenant_id, name="Burgers")
        session.add(category)
        await session.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name="Hamburguesa"
        )
        session.add(product)
        await session.flush()
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name="L", is_active=True
        )
        session.add(variant)
        await session.commit()
        await session.refresh(product)
        await session.refresh(variant)
        return product.id, variant.id


async def _create_employee(branch_id: uuid.UUID) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        person = PersonModel(first_name="Cook", last_name="Line")
        session.add(person)
        role = (await seed_rbac(session))["admin"]
        user = UserModel(
            tenant_id=tenant_id,
            email=f"cook-{uuid.uuid4().hex[:8]}@demo.com",
            hashed_password="x",
            name="Cook Line",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=role.id,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def _seed_order_with_item(
    branch_id: uuid.UUID,
    variant_id: uuid.UUID,
    *,
    channel: str = "takeaway",
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    employee_id = await _create_employee(branch_id)
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel=channel,
            employee_id=employee_id,
            status="open",
        )
        session.add(order)
        await session.flush()
        item = OrderItemModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            order_id=order.id,
            product_variant_id=variant_id,
            quantity=1,
            unit_price=Decimal("10000"),
            line_subtotal=Decimal("10000"),
            status="pending",
        )
        session.add(item)
        await session.commit()
        await session.refresh(order)
        await session.refresh(item)
        return order.id, item.id


async def _create_station(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, name: str
) -> str:
    resp = await client.post(
        "/kitchen/stations",
        headers=headers,
        json={"branch_id": str(branch_id), "name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _attach(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: uuid.UUID,
    station_id: str,
    role: str | None = None,
) -> dict:
    body: dict = {"product_id": str(product_id), "kitchen_station_id": station_id}
    if role is not None:
        body["role"] = role
    resp = await client.post("/kitchen/product-stations", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _order_state(
    client: AsyncClient, headers: dict[str, str], order_id: uuid.UUID
) -> str:
    resp = await client.get(f"/orders/{order_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["kitchen_state"]


# ============================ Station roles (2.5) ===========================
async def test_multi_station_product_each_ticket_carries_its_role(
    client: AsyncClient,
) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    grill = await _create_station(client, headers, branch_id, "Parrilla")
    cold = await _create_station(client, headers, branch_id, "Fríos")
    product_id, variant_id = await _create_product_and_variant()
    attach_grill = await _attach(client, headers, product_id, grill, "Carne y armado")
    assert attach_grill["role"] == "Carne y armado"
    await _attach(client, headers, product_id, cold, "Vegetales")

    order_id, _ = await _seed_order_with_item(branch_id, variant_id)
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 201
    tickets = routed.json()
    assert len(tickets) == 2
    roles_by_station = {t["kitchen_station_id"]: t["role"] for t in tickets}
    assert roles_by_station[grill] == "Carne y armado"
    assert roles_by_station[cold] == "Vegetales"


async def test_ticket_role_is_frozen_when_mapping_edited(client: AsyncClient) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    station = await _create_station(client, headers, branch_id, "Parrilla")
    product_id, variant_id = await _create_product_and_variant()
    await _attach(client, headers, product_id, station, "Rol original")
    order_id, _ = await _seed_order_with_item(branch_id, variant_id)
    await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)

    # Edit the mapping's role AFTER the ticket exists.
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        mapping = (
            await session.execute(
                select(ProductStationModel).where(
                    ProductStationModel.tenant_id == tenant_id,
                    ProductStationModel.product_id == product_id,
                )
            )
        ).scalar_one()
        mapping.role = "Rol editado"
        await session.commit()

    # Re-route is idempotent and must NOT rewrite the frozen ticket role.
    again = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert again.json() == []
    board = await client.get(
        f"/kitchen/stations/{station}/tickets", headers=headers
    )
    assert board.json()[0]["role"] == "Rol original"


async def test_omitted_role_is_null(client: AsyncClient) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    station = await _create_station(client, headers, branch_id, "Parrilla")
    product_id, variant_id = await _create_product_and_variant()
    mapping = await _attach(client, headers, product_id, station)
    assert mapping["role"] is None
    order_id, _ = await _seed_order_with_item(branch_id, variant_id)
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.json()[0]["role"] is None


# ============================ Ready rollup (4.8) ============================
def test_derive_kitchen_state_pure() -> None:
    assert derive_kitchen_state([]) == "none"
    assert derive_kitchen_state(["ready", "ready"]) == "ready"
    assert derive_kitchen_state(["ready", "pending"]) == "in_kitchen"
    # cancelled tickets are ignored; all remaining ready -> ready
    assert derive_kitchen_state(["ready", "cancelled"]) == "ready"
    assert derive_kitchen_state(["cancelled"]) == "none"


async def _route_and_advance(
    client: AsyncClient, headers: dict[str, str], ticket_id: str
) -> None:
    await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)


async def test_mixed_states_in_kitchen_all_ready_flags_order(
    client: AsyncClient,
) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    grill = await _create_station(client, headers, branch_id, "Parrilla")
    cold = await _create_station(client, headers, branch_id, "Fríos")
    product_id, variant_id = await _create_product_and_variant()
    await _attach(client, headers, product_id, grill)
    await _attach(client, headers, product_id, cold)
    order_id, _ = await _seed_order_with_item(branch_id, variant_id)
    tickets = (
        await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    ).json()
    assert await _order_state(client, headers, order_id) == "in_kitchen"

    # Advance only the first ticket to ready -> still in_kitchen.
    await _route_and_advance(client, headers, tickets[0]["id"])
    assert await _order_state(client, headers, order_id) == "in_kitchen"

    # Advance the last remaining ticket -> order flips to ready.
    await _route_and_advance(client, headers, tickets[1]["id"])
    assert await _order_state(client, headers, order_id) == "ready"


async def test_never_routed_order_state_is_none(client: AsyncClient) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    _, variant_id = await _create_product_and_variant()
    order_id, _ = await _seed_order_with_item(branch_id, variant_id)
    assert await _order_state(client, headers, order_id) == "none"


async def test_add_item_after_ready_returns_to_in_kitchen(
    client: AsyncClient,
) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    station = await _create_station(client, headers, branch_id, "Parrilla")
    product_id, variant_id = await _create_product_and_variant()
    await _attach(client, headers, product_id, station)
    employee_id = await _create_employee(branch_id)
    order_id = (
        await client.post(
            "/orders",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "channel": "takeaway",
                "employee_id": str(employee_id),
            },
        )
    ).json()["id"]
    # Add a mapped item -> auto-route -> in_kitchen.
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "10000"},
    )
    assert await _order_state(client, headers, order_id) == "in_kitchen"

    ticket_id = (
        await client.get(f"/kitchen/stations/{station}/tickets", headers=headers)
    ).json()[0]["id"]
    await _route_and_advance(client, headers, ticket_id)
    assert await _order_state(client, headers, order_id) == "ready"

    # Adding another mapped item reopens the kitchen state.
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "10000"},
    )
    assert await _order_state(client, headers, order_id) == "in_kitchen"


async def test_delivery_ready_auto_creates_delivery_once(client: AsyncClient) -> None:
    await _assign_admin()
    headers = await _login(client)
    branch_id = await _create_branch()
    station = await _create_station(client, headers, branch_id, "Parrilla")
    product_id, variant_id = await _create_product_and_variant()
    await _attach(client, headers, product_id, station)
    order_id, _ = await _seed_order_with_item(branch_id, variant_id, channel="delivery")
    ticket_id = (
        await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    ).json()[0]["id"]

    await _route_and_advance(client, headers, ticket_id)
    assert await _order_state(client, headers, order_id) == "ready"

    # Exactly one delivery record was auto-created and appears in Dispatch as pending.
    got = await client.get(f"/delivery/orders/{order_id}/delivery", headers=headers)
    assert got.status_code == 200
    assert got.json()["delivery_status"] == "pending"

    # Idempotent: recomputing readiness again does not create a second record.
    await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    listing = await client.get("/delivery/deliveries", headers=headers)
    matches = [d for d in listing.json() if d["order_id"] == str(order_id)]
    assert len(matches) == 1


async def test_notify_failure_still_advances_ticket(client: AsyncClient) -> None:
    """A readiness-notify failure must not fail the ticket advance (spec 4.4)."""
    await _assign_admin()
    await _login(client)  # ensure app is warm; service-level assertion below
    branch_id = await _create_branch()
    _, variant_id = await _create_product_and_variant()
    order_id, item_id = await _seed_order_with_item(branch_id, variant_id)
    tenant_id, _ = await _demo_ids()

    class _FailingReadiness:
        async def set_order_kitchen_state(self, *_args: object) -> None:
            raise RuntimeError("orders side is down")

    async with SessionFactory() as session:
        repo = SqlAlchemyKitchenRepository(session)
        # Create a single ticket directly, then advance it to ready.
        from restaurante.modules.kitchen.domain.entities import (
            KitchenStation,
            OrderItemStation,
        )

        station = await repo.create_station(
            KitchenStation(tenant_id=tenant_id, branch_id=branch_id, name="Parrilla")
        )
        assert station.id is not None
        ticket = await repo.create_ticket(
            OrderItemStation(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_item_id=item_id,
                kitchen_station_id=station.id,
            )
        )
        assert ticket.id is not None
        service = KitchenService(repo=repo, orders_readiness=_FailingReadiness())
        await service.advance_ticket(tenant_id, ticket.id)  # -> in_progress
        advanced = await service.advance_ticket(tenant_id, ticket.id)  # -> ready
        assert advanced.status == "ready"
        assert advanced.ready_at is not None
    # order_id used only to anchor the item; readiness never persisted (notify failed).
    assert order_id is not None


async def test_delivery_create_failure_still_persists_ready(
    client: AsyncClient,
) -> None:
    """A delivery-create failure must not fail the readiness update (spec 4.7)."""
    await _assign_admin()
    await _login(client)
    branch_id = await _create_branch()
    _, variant_id = await _create_product_and_variant()
    order_id, _ = await _seed_order_with_item(branch_id, variant_id, channel="delivery")
    tenant_id, _ = await _demo_ids()

    class _FailingDispatch:
        async def ensure_delivery_for_order(self, *_args: object) -> None:
            raise RuntimeError("delivery module is down")

    async with SessionFactory() as session:
        orders = OrderService(
            repo=SqlAlchemyOrdersRepository(session),
            delivery_dispatch=_FailingDispatch(),
        )
        updated = await orders.set_kitchen_state(tenant_id, order_id, "ready")
        assert updated is not None
        assert updated.kitchen_state == "ready"

    # The ready state persisted despite the dispatch failure.
    async with SessionFactory() as session:
        model = (
            await session.execute(
                select(OrderModel).where(OrderModel.id == order_id)
            )
        ).scalar_one()
        assert model.kitchen_state == "ready"
