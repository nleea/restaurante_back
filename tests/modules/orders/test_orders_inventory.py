"""Integration tests for the orders → inventory deduction on close (via recipes)."""

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
        person = PersonModel(first_name="Sam", last_name="Server")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email="sam@demo.com",
            hashed_password="x",
            name="Sam Server",
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


async def _create_recipe_and_stock(
    variant_id: uuid.UUID,
    branch_id: uuid.UUID,
    recipe_qty: str = "150",
    initial_stock: str = "1000",
) -> uuid.UUID:
    """Create an ingredient + unit, a recipe line for the variant, and stock.

    Returns the ingredient id.
    """
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


async def _open_order_with_item(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    variant_id: uuid.UUID,
    quantity: int = 3,
) -> str:
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
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={
            "product_variant_id": str(variant_id),
            "quantity": quantity,
            "unit_price": "10000",
        },
    )
    return order_id


# --- Happy path -------------------------------------------------------------
async def test_close_deducts_recipe_times_quantity(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    ingredient_id = await _create_recipe_and_stock(variant_id, branch_id)
    order_id = await _open_order_with_item(
        client, headers, branch_id, employee_id, variant_id, quantity=3
    )

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200

    # 150 * 3 = 450 deducted from 1000 -> 550
    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock.json()["current_quantity"]) == Decimal("550")

    movements = await client.get(
        f"/inventory/branches/{branch_id}/movements/{ingredient_id}", headers=headers
    )
    sale = [m for m in movements.json() if m["reason"] == "sale"]
    assert len(sale) == 1
    assert sale[0]["type"] == "out"
    assert Decimal(sale[0]["quantity"]) == Decimal("450")
    assert sale[0]["reference_id"] == order_id


async def test_insufficient_stock_goes_negative(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    ingredient_id = await _create_recipe_and_stock(
        variant_id, branch_id, recipe_qty="150", initial_stock="100"
    )
    order_id = await _open_order_with_item(
        client, headers, branch_id, employee_id, variant_id, quantity=3
    )

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200
    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    # 100 - 450 = -350
    assert Decimal(stock.json()["current_quantity"]) == Decimal("-350")


async def test_variant_without_recipe_consumes_nothing(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()  # no recipe created
    order_id = await _open_order_with_item(
        client, headers, branch_id, employee_id, variant_id, quantity=2
    )
    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200  # no recipe -> still closes, nothing deducted


async def test_cancelled_item_not_deducted(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    ingredient_id = await _create_recipe_and_stock(
        variant_id, branch_id, recipe_qty="100", initial_stock="1000"
    )
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
    active = (
        await client.post(
            f"/orders/{order_id}/items",
            headers=headers,
            json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "1"},
        )
    ).json()["id"]
    cancelled = (
        await client.post(
            f"/orders/{order_id}/items",
            headers=headers,
            json={"product_variant_id": str(variant_id), "quantity": 5, "unit_price": "1"},
        )
    ).json()["id"]
    await client.post(
        f"/orders/items/{cancelled}/cancel",
        headers=headers,
        json={"reason": "x", "requested_by_employee_id": str(employee_id)},
    )
    assert active  # keep ref for clarity

    await client.post(f"/orders/{order_id}/close", headers=headers)
    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    # only the active item (qty 1 * 100) deducted -> 1000 - 100 = 900
    assert Decimal(stock.json()["current_quantity"]) == Decimal("900")


async def test_close_is_idempotent_for_deduction(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    ingredient_id = await _create_recipe_and_stock(variant_id, branch_id)
    order_id = await _open_order_with_item(
        client, headers, branch_id, employee_id, variant_id, quantity=2
    )

    first = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert first.status_code == 200
    again = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert again.status_code == 409  # cannot re-close

    movements = await client.get(
        f"/inventory/branches/{branch_id}/movements/{ingredient_id}", headers=headers
    )
    sale = [m for m in movements.json() if m["reason"] == "sale"]
    assert len(sale) == 1  # deducted exactly once


# --- Customer stats on close ------------------------------------------------
async def _create_customer(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/customers",
        headers=headers,
        json={"first_name": "Lina", "last_name": "Cliente"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_close_updates_customer_stats(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    await _create_recipe_and_stock(variant_id, branch_id)
    customer_id = await _create_customer(client, headers)

    order_id = (
        await client.post(
            "/orders",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "channel": "takeaway",
                "employee_id": str(employee_id),
                "customer_id": customer_id,
            },
        )
    ).json()["id"]
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 3, "unit_price": "10000"},
    )

    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200
    order_total = close.json()["total"]

    cust = (await client.get(f"/customers/{customer_id}", headers=headers)).json()
    assert cust["order_count"] == 1
    assert Decimal(cust["total_spent"]) == Decimal(order_total)
    assert cust["last_purchase_at"] is not None

    # Closing again is rejected and does not double-count.
    again = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert again.status_code == 409
    cust2 = (await client.get(f"/customers/{customer_id}", headers=headers)).json()
    assert cust2["order_count"] == 1
    assert Decimal(cust2["total_spent"]) == Decimal(order_total)


async def test_close_without_customer_leaves_stats_untouched(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    await _create_recipe_and_stock(variant_id, branch_id)
    customer_id = await _create_customer(client, headers)

    # An order with no customer_id.
    order_id = await _open_order_with_item(
        client, headers, branch_id, employee_id, variant_id, quantity=2
    )
    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200

    cust = (await client.get(f"/customers/{customer_id}", headers=headers)).json()
    assert cust["order_count"] == 0
    assert Decimal(cust["total_spent"]) == Decimal("0")
    assert cust["last_purchase_at"] is None
