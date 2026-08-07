"""Integration tests for assigning a customer to an open order.

`POST /orders/{id}/customer` attaches a registered customer to an OPEN order so it
can later be closed on credit (fiado). Rejects a closed order and an unknown customer.
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
        unit = UnitOfMeasureModel(name="unit", abbreviation="und")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id, name="Base", unit_of_measure_id=unit.id, is_active=True
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


async def _create_customer(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/customers", headers=headers, json={"first_name": "Lina", "last_name": "Cliente"}
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
    unit_price: str = "10000",
) -> str:
    await seed_open_cash_session(branch_id, employee_id)
    body = {
        "branch_id": str(branch_id),
        "channel": "takeaway",
        "employee_id": str(employee_id),
    }
    order_id = (await client.post("/orders", headers=headers, json=body)).json()["id"]
    add = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={
            "product_variant_id": str(variant_id),
            "quantity": 1,
            "unit_price": unit_price,
        },
    )
    assert add.status_code == 201, add.text
    return order_id


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


# --- Assign then fiar --------------------------------------------------------
async def test_assign_customer_then_close_on_credit(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    customer_id = await _create_customer(client, headers)
    order_id = await _open_order(client, headers, branch_id, employee_id, variant_id)

    # Assign the customer to the open order.
    assign = await client.post(
        f"/orders/{order_id}/customer",
        headers=headers,
        json={"customer_id": customer_id},
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["customer_id"] == customer_id

    # Now the unpaid order closes on that customer's credit (no payment made).
    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"

    credits = await _credits_for_order(order_id)
    assert len(credits) == 1
    assert credits[0].total_amount == Decimal("10000")
    assert str(credits[0].customer_id) == customer_id


# --- Reject a non-open order -------------------------------------------------
async def test_assign_customer_to_closed_order_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    customer_id = await _create_customer(client, headers)
    await seed_open_cash_session(branch_id, employee_id)
    # Open with a customer so it can close fully on credit, then it's closed.
    body = {
        "branch_id": str(branch_id),
        "channel": "takeaway",
        "employee_id": str(employee_id),
        "customer_id": customer_id,
    }
    order_id = (await client.post("/orders", headers=headers, json=body)).json()["id"]
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1, "unit_price": "10000"},
    )
    close = await client.post(f"/orders/{order_id}/close", headers=headers)
    assert close.status_code == 200, close.text

    # Assigning to the now-closed order is rejected.
    assign = await client.post(
        f"/orders/{order_id}/customer",
        headers=headers,
        json={"customer_id": customer_id},
    )
    assert assign.status_code == 409, assign.text


# --- Reject an unknown customer ----------------------------------------------
async def test_assign_unknown_customer_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    variant_id = await _create_variant()
    order_id = await _open_order(client, headers, branch_id, employee_id, variant_id)

    assign = await client.post(
        f"/orders/{order_id}/customer",
        headers=headers,
        json={"customer_id": str(uuid.uuid4())},
    )
    assert assign.status_code == 404, assign.text
