"""Integration tests for the Inventory API (stock + movements + RBAC + tenancy)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    UserModel,
)
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.inventory.domain.entities import InventoryMovement
from restaurante.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
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


async def _create_ingredient(name: str = "Beef") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="gram", abbreviation="g")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id, name=name, unit_of_measure_id=unit.id, is_active=True
        )
        session.add(ingredient)
        await session.commit()
        await session.refresh(ingredient)
        return ingredient.id


async def _create_employee(branch_id: uuid.UUID, email: str = "emp@demo.com") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Joe", last_name="Cook")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Joe Cook",
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


# --- Stock movements --------------------------------------------------------
async def test_stock_in_creates_and_increases(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)

    resp = await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "1000",
            "reason": "purchase",
        },
    )
    assert resp.status_code == 201, resp.text

    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert stock.status_code == 200
    assert Decimal(stock.json()["current_quantity"]) == Decimal("1000")


async def test_stock_out_decreases_and_overdraw_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)

    await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "500",
            "reason": "purchase",
        },
    )
    out = await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "out",
            "quantity": "200",
            "reason": "waste",
        },
    )
    assert out.status_code == 201
    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock.json()["current_quantity"]) == Decimal("300")

    overdraw = await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "out",
            "quantity": "999",
            "reason": "waste",
        },
    )
    assert overdraw.status_code == 409
    assert overdraw.json()["code"] == "conflict"


async def test_non_positive_quantity_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)

    resp = await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "0",
            "reason": "purchase",
        },
    )
    assert resp.status_code == 422


async def test_unknown_ingredient_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)

    resp = await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(uuid.uuid4()),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "10",
            "reason": "purchase",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


# --- Recount ----------------------------------------------------------------
async def test_recount_records_delta(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)

    await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "10",
            "reason": "purchase",
        },
    )
    recount = await client.post(
        f"/inventory/branches/{branch_id}/recounts",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "counted_quantity": "8",
        },
    )
    assert recount.status_code == 201
    assert recount.json()["type"] == "adjustment"
    assert Decimal(recount.json()["quantity"]) == Decimal("2")

    stock = await client.get(
        f"/inventory/branches/{branch_id}/stock/{ingredient_id}", headers=headers
    )
    assert Decimal(stock.json()["current_quantity"]) == Decimal("8")

    history = await client.get(
        f"/inventory/branches/{branch_id}/movements/{ingredient_id}", headers=headers
    )
    # Both the purchase (`in`) and the recount (`adjustment`) are recorded. Exact
    # ordering is not asserted here: SQLite's CURRENT_TIMESTAMP has second
    # resolution, so two movements in the same second tie (Postgres would not).
    assert {m["type"] for m in history.json()} == {"in", "adjustment"}


# --- Threshold / low-stock --------------------------------------------------
async def test_low_stock_view(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)

    await client.post(
        f"/inventory/branches/{branch_id}/movements",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "employee_id": str(employee_id),
            "type": "in",
            "quantity": "5",
            "reason": "purchase",
        },
    )
    # threshold above on-hand -> appears in low-stock
    thr = await client.put(
        f"/inventory/branches/{branch_id}/stock/threshold",
        headers=headers,
        json={"ingredient_id": str(ingredient_id), "min_stock": "20"},
    )
    assert thr.status_code == 200

    low = await client.get(
        f"/inventory/branches/{branch_id}/stock/low", headers=headers
    )
    assert low.status_code == 200
    assert any(s["ingredient_id"] == str(ingredient_id) for s in low.json())


async def test_negative_threshold_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()

    resp = await client.put(
        f"/inventory/branches/{branch_id}/stock/threshold",
        headers=headers,
        json={"ingredient_id": str(ingredient_id), "min_stock": "-1"},
    )
    assert resp.status_code == 422


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    branch_id = await _create_branch()
    resp = await client.get(
        f"/inventory/branches/{branch_id}/stock", headers=headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    ingredient_id = await _create_ingredient()
    employee_id = await _create_employee(branch_id)
    async with SessionFactory() as session:
        repo = SqlAlchemyInventoryRepository(session)
        await repo.apply_movement(
            InventoryMovement(
                tenant_id=tenant_a,
                branch_id=branch_id,
                ingredient_id=ingredient_id,
                type="in",
                reason="purchase",
                quantity=Decimal("100"),
                employee_id=employee_id,
            ),
            Decimal("100"),
        )
        assert await repo.list_stock(tenant_b, branch_id) == []
        assert len(await repo.list_stock(tenant_a, branch_id)) == 1
