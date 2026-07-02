"""Integration tests for the Purchasing API (procure-to-pay + inventory + RBAC)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.purchasing.domain.entities import Supplier
from restaurante.modules.purchasing.infrastructure.repositories import (
    SqlAlchemyPurchasingRepository,
)
from restaurante.modules.recipes.infrastructure.models import IngredientModel
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


async def _create_employee(branch_id: uuid.UUID) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Paula", last_name="Purchaser")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email="paula@demo.com",
            hashed_password="x",
            name="Paula Purchaser",
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


async def _create_ingredient_and_unit() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="kilogram", abbreviation="kg")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id, name="Beef", unit_of_measure_id=unit.id, is_active=True
        )
        session.add(ingredient)
        await session.commit()
        await session.refresh(unit)
        await session.refresh(ingredient)
        return ingredient.id, unit.id


async def _create_supplier(
    client: AsyncClient, headers: dict[str, str], name: str = "ACME"
) -> str:
    resp = await client.post(
        "/purchasing/suppliers", headers=headers, json={"name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _approved_request(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    unit_id: uuid.UUID,
) -> str:
    req = await client.post(
        "/purchasing/requests",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "requested_by_employee_id": str(employee_id),
            "items": [
                {
                    "ingredient_id": str(ingredient_id),
                    "requested_quantity": "10",
                    "unit_of_measure_id": str(unit_id),
                }
            ],
        },
    )
    assert req.status_code == 201, req.text
    request_id = req.json()["id"]
    appr = await client.post(
        f"/purchasing/requests/{request_id}/approve",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert appr.status_code == 200
    assert appr.json()["status"] == "approved"
    return request_id


# --- Suppliers + catalog ----------------------------------------------------
async def test_supplier_and_ingredient_catalog(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    supplier_id = await _create_supplier(client, headers)
    ingredient_id, unit_id = await _create_ingredient_and_unit()

    attach = await client.post(
        f"/purchasing/suppliers/{supplier_id}/ingredients",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "reference_price": "12000",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert attach.status_code == 201
    dup = await client.post(
        f"/purchasing/suppliers/{supplier_id}/ingredients",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "reference_price": "9000",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert dup.status_code == 409


# --- Request approval -------------------------------------------------------
async def test_order_requires_approved_request(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    ingredient_id, unit_id = await _create_ingredient_and_unit()
    supplier_id = await _create_supplier(client, headers)

    # pending request (not approved) -> order rejected
    req = await client.post(
        "/purchasing/requests",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "requested_by_employee_id": str(employee_id),
            "items": [
                {
                    "ingredient_id": str(ingredient_id),
                    "requested_quantity": "5",
                    "unit_of_measure_id": str(unit_id),
                }
            ],
        },
    )
    request_id = req.json()["id"]
    bad = await client.post(
        "/purchasing/orders",
        headers=headers,
        json={
            "purchase_request_id": request_id,
            "supplier_id": supplier_id,
            "items": [
                {
                    "ingredient_id": str(ingredient_id),
                    "ordered_quantity": "5",
                    "unit_price": "1000",
                    "unit_of_measure_id": str(unit_id),
                }
            ],
        },
    )
    assert bad.status_code == 409


# --- Order total + receive + inventory --------------------------------------
async def test_order_receive_feeds_inventory_and_payment(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    ingredient_id, unit_id = await _create_ingredient_and_unit()
    supplier_id = await _create_supplier(client, headers)
    request_id = await _approved_request(
        client, headers, branch_id, employee_id, ingredient_id, unit_id
    )

    order = await client.post(
        "/purchasing/orders",
        headers=headers,
        json={
            "purchase_request_id": request_id,
            "supplier_id": supplier_id,
            "items": [
                {
                    "ingredient_id": str(ingredient_id),
                    "ordered_quantity": "10",
                    "unit_price": "2000",
                    "unit_of_measure_id": str(unit_id),
                }
            ],
        },
    )
    assert order.status_code == 201
    order_id = order.json()["id"]
    assert Decimal(order.json()["total"]) == Decimal("20000")  # 10 * 2000

    items = await client.get(
        f"/purchasing/orders/{order_id}/items", headers=headers
    )
    order_item_id = items.json()[0]["id"]

    # partial receipt -> partially_received + stock +4
    r1 = await client.post(
        f"/purchasing/orders/{order_id}/receive",
        headers=headers,
        json={
            "received_by_employee_id": str(employee_id),
            "items": [{"order_item_id": order_item_id, "quantity": "4"}],
        },
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "partially_received"

    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock.json()["current_quantity"]) == Decimal("4")

    # remaining receipt -> received + stock 10
    r2 = await client.post(
        f"/purchasing/orders/{order_id}/receive",
        headers=headers,
        json={
            "received_by_employee_id": str(employee_id),
            "items": [{"order_item_id": order_item_id, "quantity": "6"}],
        },
    )
    assert r2.json()["status"] == "received"
    stock2 = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock2.json()["current_quantity"]) == Decimal("10")

    movements = await client.get(
        f"/inventory/branches/{branch_id}/movements/{ingredient_id}", headers=headers
    )
    purchases = [m for m in movements.json() if m["reason"] == "purchase"]
    assert len(purchases) == 2
    assert all(m["type"] == "in" for m in purchases)

    # payments: partial then paid
    p1 = await client.post(
        f"/purchasing/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "5000", "method": "transfer", "employee_id": str(employee_id)},
    )
    assert p1.status_code == 201
    o = await client.get("/purchasing/orders", headers=headers)
    assert next(x for x in o.json() if x["id"] == order_id)["payment_status"] == "partial"

    await client.post(
        f"/purchasing/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "15000", "method": "transfer", "employee_id": str(employee_id)},
    )
    o2 = await client.get("/purchasing/orders", headers=headers)
    assert next(x for x in o2.json() if x["id"] == order_id)["payment_status"] == "paid"


async def test_receive_non_positive_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    ingredient_id, unit_id = await _create_ingredient_and_unit()
    supplier_id = await _create_supplier(client, headers)
    request_id = await _approved_request(
        client, headers, branch_id, employee_id, ingredient_id, unit_id
    )
    order_id = (
        await client.post(
            "/purchasing/orders",
            headers=headers,
            json={
                "purchase_request_id": request_id,
                "supplier_id": supplier_id,
                "items": [
                    {
                        "ingredient_id": str(ingredient_id),
                        "ordered_quantity": "10",
                        "unit_price": "2000",
                        "unit_of_measure_id": str(unit_id),
                    }
                ],
            },
        )
    ).json()["id"]
    item_id = (
        await client.get(f"/purchasing/orders/{order_id}/items", headers=headers)
    ).json()[0]["id"]
    resp = await client.post(
        f"/purchasing/orders/{order_id}/receive",
        headers=headers,
        json={
            "received_by_employee_id": str(employee_id),
            "items": [{"order_item_id": item_id, "quantity": "0"}],
        },
    )
    assert resp.status_code == 422


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/purchasing/suppliers", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    async with SessionFactory() as session:
        repo = SqlAlchemyPurchasingRepository(session)
        await repo.create_supplier(Supplier(tenant_id=tenant_a, name="ACME"))
        assert await repo.list_suppliers(tenant_b) == []
        assert len(await repo.list_suppliers(tenant_a)) == 1


async def test_cash_purchase_payment_posts_drawer_movement(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    ingredient_id, unit_id = await _create_ingredient_and_unit()
    supplier_id = await _create_supplier(client, headers)
    request_id = await _approved_request(
        client, headers, branch_id, employee_id, ingredient_id, unit_id
    )
    order_id = (
        await client.post(
            "/purchasing/orders",
            headers=headers,
            json={
                "purchase_request_id": request_id,
                "supplier_id": supplier_id,
                "items": [
                    {
                        "ingredient_id": str(ingredient_id),
                        "ordered_quantity": "10",
                        "unit_price": "2000",
                        "unit_of_measure_id": str(unit_id),
                    }
                ],
            },
        )
    ).json()["id"]

    # A cash payment without an open session is rejected.
    rejected = await client.post(
        f"/purchasing/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "5000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert rejected.status_code == 409

    # Open the order branch's cash session, then the cash payment posts an `out` movement.
    session_id = (
        await client.post(
            "/cash/sessions",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "opened_by_employee_id": str(employee_id),
                "opening_amount": "0",
            },
        )
    ).json()["id"]
    paid = await client.post(
        f"/purchasing/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "5000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert paid.status_code == 201

    movements = (
        await client.get(f"/cash/sessions/{session_id}/movements", headers=headers)
    ).json()
    purch = [m for m in movements if m["concept"] == "purchase_payment"]
    assert len(purch) == 1
    assert purch[0]["type"] == "out"
    assert purch[0]["reference_id"] == order_id

    # A non-cash payment writes no further cash movement.
    await client.post(
        f"/purchasing/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "5000", "method": "transfer", "employee_id": str(employee_id)},
    )
    movements2 = (
        await client.get(f"/cash/sessions/{session_id}/movements", headers=headers)
    ).json()
    assert len([m for m in movements2 if m["concept"] == "purchase_payment"]) == 1
