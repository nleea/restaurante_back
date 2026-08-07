"""RBAC for the delivery address: `delivery.address` vs `delivery.manage`.

The address is captured by whoever takes the order (waiter/cashier), who must NOT thereby
gain delivery administration — `delivery.manage` also gates the branch business pin, the
delivery rings and the driver roster. These tests pin both halves of that split, plus the
backward-compatibility guarantee for roles provisioned before it existed.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.domain.permissions_catalog import BASE_ROLES
from restaurante.modules.identity.infrastructure.models import (
    PermissionModel,
    PersonModel,
    RoleModel,
    UserModel,
)
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


async def _assign_custom_role(name: str, codes: list[str]) -> None:
    """Assign a tenant role holding exactly `codes` — used to rebuild a pre-split role."""
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        await seed_rbac(session)
        await session.commit()
        role = RoleModel(tenant_id=tenant_id, name=name, description=name)
        session.add(role)
        await session.flush()
        for code in codes:
            perm = (
                await session.execute(
                    select(PermissionModel).where(PermissionModel.code == code)
                )
            ).scalar_one()
            await SqlAlchemyRbacRepository(session).add_role_permission(
                role.id, perm.id
            )
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, role.id
        )
        await session.commit()


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _branch_order() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A branch, an employee and an open delivery order to hang an address on.

    Builds its own employee rather than reusing the module's `_create_employee`, which
    assigns `admin` to the test user — that would dissolve the very permission split under
    test.
    """
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        branch = BranchModel(
            tenant_id=tenant_id, code="BA", name="Branch A", is_active=True
        )
        session.add(branch)
        person = PersonModel(first_name="Ana", last_name="Ruiz")
        session.add(person)
        other = UserModel(
            tenant_id=tenant_id,
            email=f"ana-{uuid.uuid4().hex[:8]}@demo.com",
            hashed_password="x",
            name="Ana Ruiz",
            is_active=True,
        )
        session.add(other)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            person_id=person.id,
            user_id=other.id,
            role_id=roles["waiter"].id,
        )
        session.add(employee)
        await session.flush()
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            channel="delivery",
            employee_id=employee.id,
            status="open",
            # Cocinado: estos tests son sobre el despacho, no sobre el gate de cocina.
            kitchen_state="ready",
        )
        session.add(order)
        await session.commit()
        return branch.id, employee.id, order.id


# --- The order-taker can author an address ----------------------------------


async def test_waiter_writes_and_reads_an_orders_address(client: AsyncClient) -> None:
    """The whole point: the person on the phone captures the address."""
    await _assign_role("waiter")
    headers = await _login(client)
    _, _, order_id = await _branch_order()

    created = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": "Calle 15 #10-20"},
    )
    assert created.status_code == 201, created.text
    delivery_id = created.json()["id"]
    assert created.json()["delivery_status"] == "pending"

    read = await client.get(f"/delivery/orders/{order_id}/delivery", headers=headers)
    assert read.status_code == 200
    assert read.json()["address_text"] == "Calle 15 #10-20"

    fixed = await client.patch(
        f"/delivery/deliveries/{delivery_id}",
        headers=headers,
        json={"address_text": "Calle 15 #10-22"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["address_text"] == "Calle 15 #10-22"


async def test_address_permission_grants_no_delivery_administration(
    client: AsyncClient,
) -> None:
    """`delivery.address` must not become a back door to the delivery geography."""
    await _assign_role("waiter")
    headers = await _login(client)
    branch_id, employee_id, _ = await _branch_order()

    route = await client.post(
        "/delivery/routes",
        headers=headers,
        json={"branch_id": str(branch_id), "name": "Anillo Centro", "zones": []},
    )
    assert route.status_code == 403

    settings = await client.patch(
        f"/delivery/branches/{branch_id}/settings",
        headers=headers,
        json={"latitude": "11.5444", "longitude": "-72.9072"},
    )
    assert settings.status_code == 403

    drivers = await client.post(
        f"/delivery/routes/{uuid.uuid4()}/drivers",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert drivers.status_code == 403

    run = await client.post(
        "/delivery/runs",
        headers=headers,
        json={
            "delivery_route_id": str(uuid.uuid4()),
            "employee_id": str(employee_id),
        },
    )
    assert run.status_code == 403


async def test_address_permission_does_not_open_the_dispatch_board(
    client: AsyncClient,
) -> None:
    """Reading ONE order's delivery is allowed; listing the board is not."""
    await _assign_role("waiter")
    headers = await _login(client)

    board = await client.get("/delivery/deliveries", headers=headers)
    assert board.status_code == 403


# --- Backward compatibility with the pre-split shape ------------------------


async def test_manage_only_role_still_writes_delivery_records(
    client: AsyncClient,
) -> None:
    """A role provisioned before the split holds `delivery.manage` and no `delivery.address`."""
    await _assign_custom_role(
        "legacy-dispatcher", ["delivery.read", "delivery.manage"]
    )
    headers = await _login(client)
    _, _, order_id = await _branch_order()

    created = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": "Carrera 7 #12-30"},
    )
    assert created.status_code == 201, created.text

    updated = await client.patch(
        f"/delivery/deliveries/{created.json()['id']}",
        headers=headers,
        json={"address_text": "Carrera 7 #12-31"},
    )
    assert updated.status_code == 200


async def test_no_delivery_permission_at_all_is_rejected(client: AsyncClient) -> None:
    await _assign_custom_role("kitchen-only", ["orders.read"])
    headers = await _login(client)
    _, _, order_id = await _branch_order()

    resp = await client.post(
        "/delivery/deliveries",
        headers=headers,
        json={"order_id": str(order_id), "address_text": "Calle 1"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- The catalog / base roles ------------------------------------------------


def test_base_roles_grant_address_to_order_takers() -> None:
    for role in ("waiter", "cashier", "manager"):
        assert "delivery.address" in BASE_ROLES[role], role
    # A driver consumes addresses rather than authoring them.
    assert "delivery.address" not in BASE_ROLES["courier"]
    # The split must not have widened the order-takers into delivery administration.
    for role in ("waiter", "cashier"):
        assert "delivery.manage" not in BASE_ROLES[role], role


async def test_seeding_twice_is_idempotent(setup_db: None) -> None:
    async with SessionFactory() as session:
        await seed_rbac(session)
        await session.commit()
        await seed_rbac(session)
        await session.commit()

        perms = (
            await session.execute(
                select(PermissionModel).where(
                    PermissionModel.code == "delivery.address"
                )
            )
        ).scalars().all()
        assert len(perms) == 1

        waiter = (
            await session.execute(
                select(RoleModel).where(
                    RoleModel.name == "waiter", RoleModel.is_global.is_(True)
                )
            )
        ).scalars().all()
        assert len(waiter) == 1
