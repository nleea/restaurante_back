"""Integration tests for the Kitchen API (KDS: stations, routing, board, RBAC)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


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


async def _assign_role(role_name: str) -> uuid.UUID:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )
        return roles[role_name].id


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
            tenant_id=tenant_id, category_id=category.id, name="Classic Burger"
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


async def _create_order_with_item(
    branch_id: uuid.UUID, variant_id: uuid.UUID, *, cancelled: bool = False
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed an employee, an order and one item directly. Returns (order_id, item_id)."""
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
        await session.flush()
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="takeaway",
            employee_id=employee.id,
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
            status="cancelled" if cancelled else "pending",
        )
        session.add(item)
        await session.commit()
        await session.refresh(order)
        await session.refresh(item)
        return order.id, item.id


async def _create_station(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, name: str = "Grill"
) -> str:
    resp = await client.post(
        "/kitchen/stations",
        headers=headers,
        json={"branch_id": str(branch_id), "name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Stations ---------------------------------------------------------------
async def test_station_crud(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)

    listing = await client.get(
        "/kitchen/stations", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert any(s["id"] == station_id for s in listing.json())

    upd = await client.patch(
        f"/kitchen/stations/{station_id}", headers=headers, json={"position": 5}
    )
    assert upd.status_code == 200
    assert upd.json()["position"] == 5


# --- Product ↔ station -------------------------------------------------------
async def test_product_station_attach_duplicate_detach(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, _ = await _create_product_and_variant()

    attach = await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    assert attach.status_code == 201

    dup = await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    assert dup.status_code == 409

    detach = await client.delete(
        f"/kitchen/products/{product_id}/stations/{station_id}", headers=headers
    )
    assert detach.status_code == 204
    listing = await client.get(
        f"/kitchen/products/{product_id}/stations", headers=headers
    )
    assert listing.json() == []


# --- Routing + board --------------------------------------------------------
async def test_route_creates_tickets_and_is_idempotent(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, variant_id = await _create_product_and_variant()
    await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    order_id, item_id = await _create_order_with_item(branch_id, variant_id)

    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 201
    assert len(routed.json()) == 1
    assert routed.json()[0]["status"] == "pending"

    # idempotent: routing again creates nothing new
    again = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert again.json() == []

    board = await client.get(
        f"/kitchen/stations/{station_id}/tickets", headers=headers
    )
    assert len(board.json()) == 1


async def test_route_skips_no_station_and_cancelled(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    # product mapped to station, but the item will be cancelled
    product_id, variant_id = await _create_product_and_variant()
    await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    order_id, _ = await _create_order_with_item(branch_id, variant_id, cancelled=True)
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.json() == []  # cancelled item not routed

    # a second product with NO station mapping -> no ticket
    _, variant2 = await _create_product_and_variant()
    order2, _ = await _create_order_with_item(branch_id, variant2)
    routed2 = await client.post(f"/kitchen/orders/{order2}/route", headers=headers)
    assert routed2.json() == []


async def test_ticket_lifecycle(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, variant_id = await _create_product_and_variant()
    await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    order_id, _ = await _create_order_with_item(branch_id, variant_id)
    ticket_id = (
        await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    ).json()[0]["id"]

    a1 = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert a1.json()["status"] == "in_progress"
    a2 = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert a2.json()["status"] == "ready"
    assert a2.json()["ready_at"] is not None
    a3 = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert a3.status_code == 409  # ready is terminal

    pending = await client.get(
        f"/kitchen/stations/{station_id}/tickets",
        headers=headers,
        params={"status_filter": "pending"},
    )
    assert pending.json() == []


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/kitchen/stations", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    from restaurante.modules.kitchen.domain.entities import KitchenStation

    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    async with SessionFactory() as session:
        repo = SqlAlchemyKitchenRepository(session)
        await repo.create_station(
            KitchenStation(tenant_id=tenant_a, branch_id=branch_id, name="Grill")
        )
        assert await repo.list_stations(tenant_b, branch_id) == []
        assert len(await repo.list_stations(tenant_a, branch_id)) == 1


# --- Auto-routing on item add -----------------------------------------------
async def _create_employee_only(branch_id: uuid.UUID) -> uuid.UUID:
    """Seed a standalone employee (for creating orders via the API). Returns its id."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        person = PersonModel(first_name="Mesa", last_name="Mesera")
        session.add(person)
        role = (await seed_rbac(session))["admin"]
        user = UserModel(
            tenant_id=tenant_id,
            email=f"mesa-{uuid.uuid4().hex[:8]}@demo.com",
            hashed_password="x",
            name="Mesa Mesera",
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


async def test_item_add_auto_routes_to_kitchen(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, variant_id = await _create_product_and_variant()
    await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    employee_id = await _create_employee_only(branch_id)

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

    # Adding a MAPPED item auto-routes — the ticket appears with no manual /route call.
    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "10000"},
    )
    assert add.status_code == 201
    board = await client.get(f"/kitchen/stations/{station_id}/tickets", headers=headers)
    assert len(board.json()) == 1
    assert board.json()[0]["status"] == "pending"

    # An UNMAPPED item adds fine but creates no ticket.
    _, variant2 = await _create_product_and_variant()
    add2 = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant2), "quantity": 1, "unit_price": "5000"},
    )
    assert add2.status_code == 201
    board2 = await client.get(f"/kitchen/stations/{station_id}/tickets", headers=headers)
    assert len(board2.json()) == 1  # still only the mapped item's ticket

    # The manual route is now a no-op (the order is already routed, idempotent).
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.json() == []


async def test_item_add_without_kitchen_config_is_noop(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    # No station, no product->station mapping.
    _, variant_id = await _create_product_and_variant()
    employee_id = await _create_employee_only(branch_id)
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
    # Item add still succeeds; auto-route is a silent no-op without kitchen config.
    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "10000"},
    )
    assert add.status_code == 201
