"""Branch scoping for deliveries and runs.

The bug being pinned is latent: with one branch nothing looks wrong, because
`list_deliveries`/`list_runs` filtered on `tenant_id` alone. So every test here builds TWO
branches — a single-branch fixture cannot fail these.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.delivery.infrastructure.models import (
    DeliveryRouteDriverModel,
    DeliveryRunModel,
    OrderDeliveryModel,
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


async def _assign_admin() -> uuid.UUID:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )
        return roles["admin"].id


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _branch(code: str, role_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """A branch with one employee, for building two independent sides."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code=code, name=f"Branch {code}", is_active=True
        )
        session.add(branch)
        person = PersonModel(first_name="Dan", last_name=code)
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=f"driver-{code.lower()}-{uuid.uuid4().hex[:6]}@demo.com",
            hashed_password="x",
            name=f"Dan {code}",
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


async def _order(branch_id: uuid.UUID, employee_id: uuid.UUID) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery",
            employee_id=employee_id,
            status="open",
            # Cocinado: estos tests son sobre el despacho, no sobre el gate de cocina.
            kitchen_state="ready",
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def _route_with_driver(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> str:
    route = await client.post(
        "/delivery/routes",
        headers=headers,
        json={"branch_id": str(branch_id), "name": f"Ruta {branch_id.hex[:4]}", "zones": []},
    )
    route_id = route.json()["id"]
    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    return route_id


async def _delivery_for(
    client: AsyncClient, headers: dict[str, str], order_id: uuid.UUID, address: str
) -> str:
    resp = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": address},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- The branch is derived, never claimed -----------------------------------


async def test_delivery_takes_its_orders_branch(client: AsyncClient) -> None:
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)
    order_id = await _order(branch_a, employee_a)

    # The request names no branch at all.
    delivery_id = await _delivery_for(client, headers, order_id, "Calle 1")

    async with SessionFactory() as session:
        model = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.id == uuid.UUID(delivery_id)
                )
            )
        ).scalar_one()
        assert model.branch_id == branch_a


async def test_run_and_route_driver_take_their_routes_branch(
    client: AsyncClient,
) -> None:
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)
    route_id = await _route_with_driver(client, headers, branch_a, employee_a)

    run = await client.post(
        "/delivery/runs",
        headers=headers,
        json={"delivery_route_id": route_id, "employee_id": str(employee_a)},
    )
    assert run.status_code == 201, run.text

    async with SessionFactory() as session:
        run_model = (
            await session.execute(
                select(DeliveryRunModel).where(
                    DeliveryRunModel.id == uuid.UUID(run.json()["id"])
                )
            )
        ).scalar_one()
        assert run_model.branch_id == branch_a

        driver_model = (
            await session.execute(
                select(DeliveryRouteDriverModel).where(
                    DeliveryRouteDriverModel.delivery_route_id == uuid.UUID(route_id)
                )
            )
        ).scalar_one()
        assert driver_model.branch_id == branch_a


# --- Listing is scoped ------------------------------------------------------


async def test_listing_deliveries_excludes_another_branch(client: AsyncClient) -> None:
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)
    branch_b, employee_b = await _branch("BB", role_id)

    a_delivery = await _delivery_for(
        client, headers, await _order(branch_a, employee_a), "Calle A"
    )
    b_delivery = await _delivery_for(
        client, headers, await _order(branch_b, employee_b), "Calle B"
    )

    listed_a = await client.get(
        "/delivery/deliveries", headers=headers, params={"branch_id": str(branch_a)}
    )
    ids_a = {d["id"] for d in listed_a.json()}
    assert a_delivery in ids_a
    assert b_delivery not in ids_a  # the latent bug: B used to leak into A's board

    listed_b = await client.get(
        "/delivery/deliveries", headers=headers, params={"branch_id": str(branch_b)}
    )
    ids_b = {d["id"] for d in listed_b.json()}
    assert b_delivery in ids_b
    assert a_delivery not in ids_b


async def test_listing_runs_excludes_another_branch(client: AsyncClient) -> None:
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)
    branch_b, employee_b = await _branch("BB", role_id)

    route_a = await _route_with_driver(client, headers, branch_a, employee_a)
    route_b = await _route_with_driver(client, headers, branch_b, employee_b)
    run_a = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_a, "employee_id": str(employee_a)},
        )
    ).json()["id"]
    run_b = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_b, "employee_id": str(employee_b)},
        )
    ).json()["id"]

    listed = await client.get(
        "/delivery/runs", headers=headers, params={"branch_id": str(branch_a)}
    )
    ids = {r["id"] for r in listed.json()}
    assert run_a in ids
    assert run_b not in ids


async def test_listing_without_a_branch_is_rejected(client: AsyncClient) -> None:
    """Not silently tenant-wide — the param is required, so the old bug is unaskable."""
    await _assign_admin()
    headers = await _login(client)

    assert (await client.get("/delivery/deliveries", headers=headers)).status_code == 422
    assert (await client.get("/delivery/runs", headers=headers)).status_code == 422


async def test_listing_an_unknown_branch_is_not_found(client: AsyncClient) -> None:
    await _assign_admin()
    headers = await _login(client)
    resp = await client.get(
        "/delivery/deliveries", headers=headers, params={"branch_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


# --- The cross-branch hole the column makes visible --------------------------


async def test_assigning_across_branches_is_rejected(client: AsyncClient) -> None:
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)
    branch_b, employee_b = await _branch("BB", role_id)

    # A delivery of branch A, a run of branch B.
    delivery_id = await _delivery_for(
        client, headers, await _order(branch_a, employee_a), "Calle A"
    )
    route_b = await _route_with_driver(client, headers, branch_b, employee_b)
    run_b = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_b, "employee_id": str(employee_b)},
        )
    ).json()["id"]

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_b},
    )
    assert resp.status_code == 409

    # Nothing moved.
    async with SessionFactory() as session:
        model = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.id == uuid.UUID(delivery_id)
                )
            )
        ).scalar_one()
        assert model.delivery_run_id is None
        assert model.delivery_status == "pending"


async def test_assigning_within_a_branch_still_works(client: AsyncClient) -> None:
    """Guards against the new check over-rejecting the normal path."""
    role_id = await _assign_admin()
    headers = await _login(client)
    branch_a, employee_a = await _branch("BA", role_id)

    delivery_id = await _delivery_for(
        client, headers, await _order(branch_a, employee_a), "Calle A"
    )
    route_a = await _route_with_driver(client, headers, branch_a, employee_a)
    run_a = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_a, "employee_id": str(employee_a)},
        )
    ).json()["id"]

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_a},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_status"] == "assigned"
