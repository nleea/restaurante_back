"""Integration tests for the Orders API (lifecycle core + RBAC + tenancy)."""

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
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
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


async def _create_branch(code: str = "B1") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code=code, name=f"Branch {code}", is_active=True
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def _create_employee(branch_id: uuid.UUID, email: str = "waiter@demo.com") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Will", last_name="Waiter")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Will Waiter",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def _create_variant(name: str = "Classic - L") -> uuid.UUID:
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
            tenant_id=tenant_id, product_id=product.id, name=name, is_active=True
        )
        session.add(variant)
        await session.commit()
        await session.refresh(variant)
        return variant.id


async def _create_addon(name: str = "Cheese", price: str = "2000") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        addon = AddonModel(
            tenant_id=tenant_id, name=name, price=Decimal(price), is_active=True
        )
        session.add(addon)
        await session.commit()
        await session.refresh(addon)
        return addon.id


async def _setup_order(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    table_resp = await client.post(
        "/orders/tables",
        headers=headers,
        json={"branch_id": str(branch_id), "number": "1", "capacity": 4},
    )
    assert table_resp.status_code == 201, table_resp.text
    table_id = table_resp.json()["id"]
    order_resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "dine_in",
            "employee_id": str(employee_id),
            "dining_table_id": str(table_id),
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    return {
        "branch_id": str(branch_id),
        "employee_id": str(employee_id),
        "variant_id": str(variant_id),
        "table_id": table_id,
        "order_id": order_resp.json()["id"],
    }


# --- Tables -----------------------------------------------------------------
async def test_table_duplicate_number_conflict(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    body = {"branch_id": str(branch_id), "number": "5", "capacity": 4}
    first = await client.post("/orders/tables", headers=headers, json=body)
    assert first.status_code == 201
    dup = await client.post("/orders/tables", headers=headers, json=body)
    assert dup.status_code == 409


# --- Order lifecycle --------------------------------------------------------
async def test_open_marks_table_occupied(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    tables = await client.get(
        "/orders/tables", headers=headers, params={"branch_id": ctx["branch_id"]}
    )
    occupied = next(t for t in tables.json() if t["id"] == ctx["table_id"])
    assert occupied["status"] == "occupied"


async def test_bad_channel_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "carrier_pigeon",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 422


async def test_unknown_employee_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "takeaway",
            "employee_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404


async def test_items_and_totals_recompute(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    order_id, variant_id = ctx["order_id"], ctx["variant_id"]

    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": variant_id, "quantity": 2, "unit_price": "10000"},
    )
    assert add.status_code == 201
    item_id = add.json()["id"]
    assert Decimal(add.json()["line_subtotal"]) == Decimal("20000")

    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert Decimal(order.json()["subtotal"]) == Decimal("20000")
    assert Decimal(order.json()["total"]) == Decimal("20000")

    # addon increases line + totals
    addon_id = await _create_addon()
    attach = await client.post(
        f"/orders/items/{item_id}/addons",
        headers=headers,
        json={"addon_id": str(addon_id), "applied_price": "2000"},
    )
    assert attach.status_code == 201
    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert Decimal(order.json()["subtotal"]) == Decimal("22000")

    # update quantity to 1 -> line = 10000 + 2000 addon = 12000
    upd = await client.patch(
        f"/orders/items/{item_id}", headers=headers, json={"quantity": 1}
    )
    assert Decimal(upd.json()["line_subtotal"]) == Decimal("12000")

    # discount
    disc = await client.put(
        f"/orders/{order_id}/discount", headers=headers, json={"discount": "2000"}
    )
    assert Decimal(disc.json()["total"]) == Decimal("10000")

    # discount above subtotal -> 422
    bad = await client.put(
        f"/orders/{order_id}/discount", headers=headers, json={"discount": "999999"}
    )
    assert bad.status_code == 422

    # remove item -> totals back to 0
    rm = await client.delete(f"/orders/items/{item_id}", headers=headers)
    assert rm.status_code == 204
    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert Decimal(order.json()["subtotal"]) == Decimal("0")


async def test_add_item_to_closed_order_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    order_id = ctx["order_id"]

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200
    assert close.json()["status"] == "closed"
    assert close.json()["closed_at"] is not None

    # table freed
    tables = await client.get(
        "/orders/tables", headers=headers, params={"branch_id": ctx["branch_id"]}
    )
    freed = next(t for t in tables.json() if t["id"] == ctx["table_id"])
    assert freed["status"] == "free"

    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={
            "product_variant_id": ctx["variant_id"],
            "quantity": 1,
            "unit_price": "5000",
        },
    )
    assert add.status_code == 409


async def test_cancel_order_frees_table(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    resp = await client.post(
        f"/orders/{ctx['order_id']}/cancel",
        headers=headers,
        json={"reason": "client left", "requested_by_employee_id": ctx["employee_id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    tables = await client.get(
        "/orders/tables", headers=headers, params={"branch_id": ctx["branch_id"]}
    )
    freed = next(t for t in tables.json() if t["id"] == ctx["table_id"])
    assert freed["status"] == "free"


async def test_cancel_item_recomputes(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    order_id = ctx["order_id"]
    item_id = (
        await client.post(
            f"/orders/{order_id}/items",
            headers=headers,
            json={
                "product_variant_id": ctx["variant_id"],
                "quantity": 1,
                "unit_price": "8000",
            },
        )
    ).json()["id"]

    cancel = await client.post(
        f"/orders/items/{item_id}/cancel",
        headers=headers,
        json={"reason": "wrong dish", "requested_by_employee_id": ctx["employee_id"]},
    )
    assert cancel.status_code == 204
    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert Decimal(order.json()["subtotal"]) == Decimal("0")


async def test_receipt_first_then_reprint(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    ctx = await _setup_order(client, headers)
    order_id = ctx["order_id"]
    first = await client.post(
        f"/orders/{order_id}/receipts",
        headers=headers,
        json={"employee_id": ctx["employee_id"]},
    )
    assert first.status_code == 201
    assert first.json()["is_reprint"] is False
    second = await client.post(
        f"/orders/{order_id}/receipts",
        headers=headers,
        json={"employee_id": ctx["employee_id"]},
    )
    assert second.json()["is_reprint"] is True


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/orders", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    from restaurante.modules.orders.domain.entities import Order

    async with SessionFactory() as session:
        repo = SqlAlchemyOrdersRepository(session)
        await repo.create_order(
            Order(
                tenant_id=tenant_a,
                branch_id=branch_id,
                channel="takeaway",
                employee_id=employee_id,
            )
        )
        assert await repo.list_orders(tenant_b) == []
        assert len(await repo.list_orders(tenant_a)) == 1
