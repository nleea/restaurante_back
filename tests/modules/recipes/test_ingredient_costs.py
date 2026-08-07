"""Integration tests for the menu-facing ingredient unit-cost read.

Covers the `product-costing` delta: `GET /recipes/ingredient-costs` surfaces each
ingredient's moving-average purchase cost for the live food-cost meter, reporting
an ingredient with no purchase history as `null` (unavailable, never zeroed).
"""

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
from restaurante.modules.purchasing.infrastructure.models import (
    PurchaseOrderItemModel,
    PurchaseOrderModel,
    PurchaseRequestModel,
    SupplierModel,
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


async def _create_unit(abbr: str = "kg") -> uuid.UUID:
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="kilogram", abbreviation=abbr)
        session.add(unit)
        await session.commit()
        await session.refresh(unit)
        return unit.id


async def _create_ingredient(unit_id: uuid.UUID, name: str) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        ingredient = IngredientModel(
            tenant_id=tenant_id, name=name, unit_of_measure_id=unit_id, is_active=True
        )
        session.add(ingredient)
        await session.commit()
        await session.refresh(ingredient)
        return ingredient.id


async def _create_branch_and_employee() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True
        )
        session.add(branch)
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
            branch_id=branch.id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
        )
        session.add(employee)
        await session.commit()
        return branch.id, employee.id


async def _seed_purchase_history(
    ingredient_id: uuid.UUID, unit_id: uuid.UUID, unit_prices: list[str]
) -> None:
    """Insert a minimal purchase chain so the ingredient has purchase lines."""
    tenant_id, _ = await _demo_ids()
    branch_id, employee_id = await _create_branch_and_employee()
    async with SessionFactory() as session:
        supplier = SupplierModel(tenant_id=tenant_id, name="ACME")
        session.add(supplier)
        request = PurchaseRequestModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            requested_by_employee_id=employee_id,
        )
        session.add(request)
        await session.flush()
        order = PurchaseOrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            purchase_request_id=request.id,
            supplier_id=supplier.id,
        )
        session.add(order)
        await session.flush()
        for price in unit_prices:
            session.add(
                PurchaseOrderItemModel(
                    tenant_id=tenant_id,
                    purchase_order_id=order.id,
                    ingredient_id=ingredient_id,
                    ordered_quantity=Decimal("1"),
                    unit_price=Decimal(price),
                    unit_of_measure_id=unit_id,
                )
            )
        await session.commit()


async def test_ingredient_costs_null_without_purchase_history(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    beef = await _create_ingredient(unit_id, "Beef")
    cheese = await _create_ingredient(unit_id, "Cheese")

    resp = await client.get("/recipes/ingredient-costs", headers=headers)
    assert resp.status_code == 200, resp.text
    by_id = {row["ingredient_id"]: row for row in resp.json()}

    # Both ingredients are reported, and an unavailable cost is null — not zero.
    assert by_id[str(beef)]["unit_cost"] is None
    assert by_id[str(cheese)]["unit_cost"] is None


async def test_ingredient_cost_is_moving_average_of_purchases(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    beef = await _create_ingredient(unit_id, "Beef")
    await _seed_purchase_history(beef, unit_id, ["10000", "20000"])

    resp = await client.get("/recipes/ingredient-costs", headers=headers)
    assert resp.status_code == 200, resp.text
    by_id = {row["ingredient_id"]: row for row in resp.json()}

    assert Decimal(by_id[str(beef)]["unit_cost"]) == Decimal("15000")


async def test_ingredient_costs_requires_read_permission(client: AsyncClient) -> None:
    # Logged in but without recipes.read (cashier lacks it).
    await _assign_role("cashier")
    headers = await _login(client)
    resp = await client.get("/recipes/ingredient-costs", headers=headers)
    assert resp.status_code == 403, resp.text
