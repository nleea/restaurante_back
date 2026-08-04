"""Integration tests for the require-payment-or-credit gate on closing an order.

Closing an `open` order now requires it to be settled: payments must cover the
`total`, unless the order has a registered customer, in which case the unpaid
remainder closes on credit (fiado) and lands as a pending `customer_credit`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.customers.infrastructure.models import CustomerCreditModel
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.inventory.infrastructure.models import InventoryStockModel
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD
from tests.modules._cash import seed_open_cash_session


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
        person = PersonModel(first_name="Cara", last_name="Cajera")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email="cara@demo.com",
            hashed_password="x",
            name="Cara Cajera",
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


async def _create_variant() -> uuid.UUID:
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
        await session.flush()
        # A sellable variant must have a recipe (order add-item safety net); give it one.
        unit = UnitOfMeasureModel(name="unit", abbreviation="und")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id,
            name="Base",
            unit_of_measure_id=unit.id,
            is_active=True,
        )
        session.add(ingredient)
        await session.flush()
        session.add(
            RecipeItemModel(
                tenant_id=tenant_id,
                product_variant_id=variant.id,
                ingredient_id=ingredient.id,
                quantity=Decimal("1"),
                unit_of_measure_id=unit.id,
            )
        )
        await session.commit()
        await session.refresh(variant)
        return variant.id


async def _create_recipe_and_stock(
    variant_id: uuid.UUID,
    branch_id: uuid.UUID,
    recipe_qty: str = "150",
    initial_stock: str = "1000",
) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="gram", abbreviation="g")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id, name="Beef", unit_of_measure_id=unit.id, is_active=True
        )
        session.add(ingredient)
        await session.flush()
        session.add(
            RecipeItemModel(
                tenant_id=tenant_id,
                product_variant_id=variant_id,
                ingredient_id=ingredient.id,
                quantity=Decimal(recipe_qty),
                unit_of_measure_id=unit.id,
            )
        )
        session.add(
            InventoryStockModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=ingredient.id,
                current_quantity=Decimal(initial_stock),
                min_stock=Decimal(0),
            )
        )
        await session.commit()
        await session.refresh(ingredient)
        return ingredient.id


async def _create_customer(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/customers",
        headers=headers,
        json={"first_name": "Lina", "last_name": "Cliente"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _open_order(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    variant_id: uuid.UUID,
    *,
    customer_id: str | None = None,
    quantity: int = 1,
    unit_price: str = "10000",
) -> str:
    """Open an order (optionally for a customer) with a single line item."""
    body: dict[str, str] = {
        "branch_id": str(branch_id),
        "channel": "takeaway",
        "employee_id": str(employee_id),
    }
    if customer_id is not None:
        body["customer_id"] = customer_id
    order_id = (await client.post("/orders", headers=headers, json=body)).json()["id"]
    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={
            "product_variant_id": str(variant_id),
            "quantity": quantity,
            "unit_price": unit_price,
        },
    )
    assert add.status_code == 201, add.text
    return order_id


async def _open_cash_session(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    resp = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(employee_id),
            "opening_amount": "0",
        },
    )
    assert resp.status_code == 201, resp.text


async def _pay(
    client: AsyncClient,
    headers: dict[str, str],
    order_id: str,
    employee_id: uuid.UUID,
    amount: str,
) -> None:
    resp = await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": amount, "method": "cash", "employee_id": str(employee_id)},
    )
    assert resp.status_code == 201, resp.text


async def _credits_for_order(order_id: str) -> list[CustomerCreditModel]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(CustomerCreditModel).where(
                    CustomerCreditModel.reference_id == uuid.UUID(order_id)
                )
            )
        ).scalars()
        return list(rows)


# --- Fully paid -------------------------------------------------------------
async def test_close_fully_paid_order_ok(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(
        client, headers, branch_id, employee_id, variant_id, unit_price="10000"
    )
    await _pay(client, headers, order_id, employee_id, "10000")

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"
    assert await _credits_for_order(order_id) == []


# --- Overpayment (change) ---------------------------------------------------
async def test_close_overpaid_order_ok_no_credit(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(
        client, headers, branch_id, employee_id, variant_id, unit_price="10000"
    )
    await _pay(client, headers, order_id, employee_id, "15000")  # $5000 change

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"
    assert await _credits_for_order(order_id) == []


# --- Underpaid, no customer -> rejected -------------------------------------
async def test_close_underpaid_no_customer_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    ingredient_id = await _create_recipe_and_stock(variant_id, branch_id)
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(
        client, headers, branch_id, employee_id, variant_id, unit_price="10000"
    )
    await _pay(client, headers, order_id, employee_id, "4000")  # remainder 6000

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 422, close.text
    assert close.json()["code"] == "validation_error"
    assert "6000" in close.json()["detail"]

    # Order stays open.
    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert order.json()["status"] == "open"
    # No inventory was deducted (stock untouched).
    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock.json()["current_quantity"]) == Decimal("1000")
    # No credit created.
    assert await _credits_for_order(order_id) == []


# --- Underpaid, with customer -> closes on credit ---------------------------
async def test_close_underpaid_with_customer_creates_credit(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    customer_id = await _create_customer(client, headers)
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(
        client,
        headers,
        branch_id,
        employee_id,
        variant_id,
        customer_id=customer_id,
        unit_price="10000",
    )
    await _pay(client, headers, order_id, employee_id, "4000")  # remainder 6000

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"

    credits = await _credits_for_order(order_id)
    assert len(credits) == 1
    credit = credits[0]
    assert credit.total_amount == Decimal("6000")
    assert credit.payment_status == "pending"
    assert str(credit.customer_id) == customer_id
    assert str(credit.reference_id) == order_id


# --- Fully on credit (no payment) -------------------------------------------
async def test_close_fully_on_credit_creates_credit_for_total(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    customer_id = await _create_customer(client, headers)
    # Opening an order needs an open drawer; the order still closes fully on credit.
    await seed_open_cash_session(branch_id, employee_id)
    order_id = await _open_order(
        client,
        headers,
        branch_id,
        employee_id,
        variant_id,
        customer_id=customer_id,
        unit_price="10000",
    )

    # No payment: the whole total goes on credit.
    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"

    credits = await _credits_for_order(order_id)
    assert len(credits) == 1
    assert credits[0].total_amount == Decimal("10000")
    assert str(credits[0].reference_id) == order_id
