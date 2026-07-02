"""Integration tests for the Delivery API (routes, drivers, runs, lifecycle, RBAC)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
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


async def _create_employee(branch_id: uuid.UUID, email: str) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Dan", last_name="Driver")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Dan Driver",
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


async def _create_order(branch_id: uuid.UUID, employee_id: uuid.UUID) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery",
            employee_id=employee_id,
            status="open",
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def _create_route(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID
) -> str:
    resp = await client.post(
        "/delivery/routes",
        headers=headers,
        json={"branch_id": str(branch_id), "name": "North"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Routes + drivers -------------------------------------------------------
async def test_route_and_driver_flow(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, "d1@demo.com")

    attach = await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    assert attach.status_code == 201

    dup = await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    assert dup.status_code == 409

    drivers = await client.get(
        f"/delivery/routes/{route_id}/drivers", headers=headers
    )
    assert len(drivers.json()) == 1


# --- Deliveries -------------------------------------------------------------
async def test_delivery_create_one_per_order(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id, "d2@demo.com")
    order_id = await _create_order(branch_id, employee_id)

    first = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": "Calle 1 #2-3"},
    )
    assert first.status_code == 201
    assert first.json()["delivery_status"] == "pending"

    dup = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": "otra"},
    )
    assert dup.status_code == 409


async def test_run_requires_driver_on_route(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    employee_id = await _create_employee(branch_id, "d3@demo.com")

    # not assigned to the route yet -> reject
    bad = await client.post(
        "/delivery/runs",
        headers=headers,
        json={"delivery_route_id": route_id, "employee_id": str(employee_id)},
    )
    assert bad.status_code == 422

    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    ok = await client.post(
        "/delivery/runs",
        headers=headers,
        json={"delivery_route_id": route_id, "employee_id": str(employee_id)},
    )
    assert ok.status_code == 201
    assert ok.json()["status"] == "preparing"


# --- Full lifecycle ---------------------------------------------------------
async def test_assign_depart_deliver_finish(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, "d4@demo.com")
    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    run_id = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_id, "employee_id": str(driver)},
        )
    ).json()["id"]
    order_id = await _create_order(branch_id, driver)
    delivery_id = (
        await client.post(
            "/delivery/deliveries",
            headers=headers,
            json={"order_id": str(order_id), "address_text": "Calle 9"},
        )
    ).json()["id"]

    # assign
    assigned = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["delivery_status"] == "assigned"
    assert assigned.json()["delivery_route_id"] == route_id

    # depart -> cascades to in_transit
    departed = await client.post(f"/delivery/runs/{run_id}/depart", headers=headers)
    assert departed.status_code == 200
    assert departed.json()["status"] == "in_transit"
    d = await client.get(
        f"/delivery/orders/{order_id}/delivery", headers=headers
    )
    assert d.json()["delivery_status"] == "in_transit"

    # mark delivered
    delivered = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )
    assert delivered.status_code == 200
    assert delivered.json()["delivery_status"] == "delivered"
    assert delivered.json()["delivered_at"] is not None

    # finish run
    finished = await client.post(f"/delivery/runs/{run_id}/finish", headers=headers)
    assert finished.json()["status"] == "finished"


async def test_assign_to_departed_run_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, "d5@demo.com")
    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    run_id = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_id, "employee_id": str(driver)},
        )
    ).json()["id"]
    await client.post(f"/delivery/runs/{run_id}/depart", headers=headers)

    order_id = await _create_order(branch_id, driver)
    delivery_id = (
        await client.post(
            "/delivery/deliveries",
            headers=headers,
            json={"order_id": str(order_id), "address_text": "x"},
        )
    ).json()["id"]
    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )
    assert resp.status_code == 409


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/delivery/routes", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    from restaurante.modules.delivery.domain.entities import DeliveryRoute

    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    async with SessionFactory() as session:
        repo = SqlAlchemyDeliveryRepository(session)
        await repo.create_route(
            DeliveryRoute(tenant_id=tenant_a, branch_id=branch_id, name="North")
        )
        assert await repo.list_routes(tenant_b, branch_id) == []
        assert len(await repo.list_routes(tenant_a, branch_id)) == 1
