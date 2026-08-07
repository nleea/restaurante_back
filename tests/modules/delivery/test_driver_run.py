"""Driver self-service run: `delivery.drive` + ownership over `/delivery/me/...`.

A courier opens (self-create + pull) their OWN despacho, reads it order-enriched, departs,
marks stops delivered / not-delivered with a reason, unassigns a wrongly-pulled drop while
still preparing, and finishes — never touching another driver's run and never holding the
dispatcher's `delivery.assign` / `delivery.manage`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.delivery.infrastructure.models import (
    DeliveryRouteDriverModel,
    DeliveryRouteModel,
    DeliveryRunModel,
    OrderDeliveryModel,
)
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
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
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


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@dataclass
class Ctx:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    route_ids: list[uuid.UUID]


async def _make_driver(
    *, role: str | None = "courier", routes: int = 1, link_employee: bool = True
) -> Ctx:
    """Seed RBAC, make the demo user a courier employee, and (optionally) an active
    driver of `routes` route(s) in a fresh branch — the one-time admin setup."""
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        seeded = await seed_rbac(session)
        await session.commit()
        if role is not None:
            await SqlAlchemyRbacRepository(session).assign_user_role(
                tenant_id, user_id, seeded[role].id
            )
            await session.commit()

        branch = BranchModel(
            tenant_id=tenant_id, code=f"B{uuid.uuid4().hex[:4]}", name="B", is_active=True
        )
        session.add(branch)
        await session.flush()

        employee_id = uuid.uuid4()
        route_ids: list[uuid.UUID] = []
        if link_employee:
            person = PersonModel(first_name="Dee", last_name="Driver")
            session.add(person)
            await session.flush()
            employee = EmployeeModel(
                id=employee_id,
                tenant_id=tenant_id,
                branch_id=branch.id,
                person_id=person.id,
                user_id=user_id,
                role_id=seeded[role].id if role else seeded["courier"].id,
            )
            session.add(employee)
            await session.flush()
            for i in range(routes):
                route = DeliveryRouteModel(
                    tenant_id=tenant_id,
                    branch_id=branch.id,
                    name=f"R{i}",
                    zones=[],
                    position=i,
                )
                session.add(route)
                await session.flush()
                session.add(
                    DeliveryRouteDriverModel(
                        tenant_id=tenant_id,
                        branch_id=branch.id,
                        delivery_route_id=route.id,
                        employee_id=employee.id,
                    )
                )
                route_ids.append(route.id)
            # Caja abierta: entregar un pedido en efectivo cobra en la puerta, y cobrar
            # exige sesión abierta. Sin ella el mark-delivered se rechaza — que es lo
            # correcto, pero no es lo que prueban estos tests del run.
            session.add(
                CashSessionModel(
                    tenant_id=tenant_id,
                    branch_id=branch.id,
                    opened_by_employee_id=employee_id,
                    opening_amount=Decimal("0"),
                    status="open",
                )
            )
        await session.commit()
        return Ctx(tenant_id, branch.id, employee_id, route_ids)


async def _pending_delivery(
    branch_id: uuid.UUID,
    *,
    address: str = "Calle 1",
    route_position: int | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A branch order + its pending, unassigned delivery. Returns (order_id, delivery_id)."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery",
            employee_id=(
                await session.execute(
                    select(EmployeeModel.id).where(EmployeeModel.tenant_id == tenant_id)
                )
            ).scalars().first(),
            status="open",
            # Cocinado: estos tests son sobre el despacho, no sobre el gate de cocina.
            kitchen_state="ready",
            total=Decimal("25000"),
        )
        session.add(order)
        await session.flush()
        delivery = OrderDeliveryModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            order_id=order.id,
            address_text=address,
            delivery_status="pending",
            route_position=route_position,
        )
        session.add(delivery)
        await session.commit()
        return order.id, delivery.id


# --- Catalog / base roles ---------------------------------------------------
def test_courier_base_role_holds_drive_not_address() -> None:
    assert "delivery.drive" in BASE_ROLES["courier"]
    assert "delivery.address" not in BASE_ROLES["courier"]
    # A driver never gains the dispatcher permissions.
    assert "delivery.assign" not in BASE_ROLES["courier"]
    assert "delivery.manage" not in BASE_ROLES["courier"]


async def test_seed_grants_drive_to_courier_and_is_idempotent(
    setup_db: None,
) -> None:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await seed_rbac(session)  # re-seed changes nothing further
        await session.commit()

        # Exactly one permission row and one global courier role after two seeds.
        perms = (
            await session.execute(
                select(PermissionModel).where(PermissionModel.code == "delivery.drive")
            )
        ).scalars().all()
        assert len(perms) == 1
        courier = (
            await session.execute(
                select(RoleModel).where(
                    RoleModel.name == "courier", RoleModel.is_global.is_(True)
                )
            )
        ).scalars().all()
        assert len(courier) == 1

        # The courier role grants delivery.drive but never delivery.address.
        repo = SqlAlchemyRbacRepository(session)
        await repo.assign_user_role(tenant_id, user_id, roles["courier"].id)
        codes = await repo.effective_permission_codes(tenant_id, user_id)
        assert "delivery.drive" in codes
        assert "delivery.address" not in codes


# --- Self-open + pull -------------------------------------------------------
async def test_self_open_pulls_only_eligible_zone_agnostic(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    # Two pending (eligible) + one already assigned to another run (not eligible).
    _, d1 = await _pending_delivery(ctx.branch_id, address="A")
    _, d2 = await _pending_delivery(ctx.branch_id, address="B")
    other_order, d3 = await _pending_delivery(ctx.branch_id, address="C")
    async with SessionFactory() as session:
        # A run owned by a DIFFERENT employee holds d3 (so it must not be pulled).
        other = EmployeeModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            person_id=(
                await _new_person(session)
            ),
            user_id=(await _new_user(session, ctx.tenant_id)),
            role_id=(
                await session.execute(select(EmployeeModel.role_id))
            ).scalars().first(),
        )
        session.add(other)
        await session.flush()
        other_run = DeliveryRunModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            delivery_route_id=ctx.route_ids[0],
            employee_id=other.id,
            status="preparing",
        )
        session.add(other_run)
        await session.flush()
        d3_model = (
            await session.execute(
                select(OrderDeliveryModel).where(OrderDeliveryModel.id == d3)
            )
        ).scalar_one()
        d3_model.delivery_run_id = other_run.id
        d3_model.delivery_status = "assigned"
        await session.commit()

    resp = await client.post("/delivery/me/run", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "preparing"
    stop_ids = {s["id"] for s in body["stops"]}
    assert stop_ids == {str(d1), str(d2)}  # the assigned d3 was left untouched


async def test_second_open_is_idempotent(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    await _pending_delivery(ctx.branch_id)
    first = await client.post("/delivery/me/run", headers=headers, json={})
    second = await client.post("/delivery/me/run", headers=headers, json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_open_without_route_is_rejected(client: AsyncClient) -> None:
    await _make_driver(routes=0)  # employee exists, no route link
    headers = await _login(client)
    resp = await client.post("/delivery/me/run", headers=headers, json={})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_open_multi_route_requires_choice(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=2)
    headers = await _login(client)
    ambiguous = await client.post("/delivery/me/run", headers=headers, json={})
    assert ambiguous.status_code == 422

    chosen = await client.post(
        "/delivery/me/run",
        headers=headers,
        json={"delivery_route_id": str(ctx.route_ids[1])},
    )
    assert chosen.status_code == 200
    assert chosen.json()["delivery_route_id"] == str(ctx.route_ids[1])


async def test_list_my_routes_returns_my_active_routes(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=2)
    headers = await _login(client)
    resp = await client.get("/delivery/me/routes", headers=headers)
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert ids == {str(rid) for rid in ctx.route_ids}


async def test_list_my_routes_requires_drive(client: AsyncClient) -> None:
    await _make_driver(routes=1, role=None)  # employee, but no delivery.drive
    headers = await _login(client)
    resp = await client.get("/delivery/me/routes", headers=headers)
    assert resp.status_code == 403


# --- Read my run (enriched, ordered, caller-only) ---------------------------
async def test_get_my_run_empty_when_none(client: AsyncClient) -> None:
    await _make_driver(routes=1)
    headers = await _login(client)
    resp = await client.get("/delivery/me/run", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_my_run_is_enriched_and_position_ordered(
    client: AsyncClient,
) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    # Two stops with explicit positions (2 then 1) to prove ordering.
    o_late, _ = await _enriched_order(ctx, position=2, name="Bob", phone="300")
    o_early, _ = await _enriched_order(ctx, position=1, name="Ana", phone="311")

    await client.post("/delivery/me/run", headers=headers, json={})
    resp = await client.get("/delivery/me/run", headers=headers)
    assert resp.status_code == 200
    stops = resp.json()["stops"]
    assert [s["order_id"] for s in stops] == [str(o_early), str(o_late)]
    first = stops[0]
    assert first["customer_name"] == "Ana Ruiz"
    assert first["customer_phone"] == "311"
    assert first["order_code"] is not None
    assert first["total"] == "25000.00"
    assert first["payment_method"] == "cash"
    assert first["paid"] is True
    assert first["items"] == [{"name": "Burger", "quantity": 2}]


async def test_get_my_run_is_caller_only(client: AsyncClient) -> None:
    """Another driver's active run is never returned as 'my run'."""
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    async with SessionFactory() as session:
        other = EmployeeModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            person_id=await _new_person(session),
            user_id=await _new_user(session, ctx.tenant_id),
            role_id=(
                await session.execute(select(EmployeeModel.role_id))
            ).scalars().first(),
        )
        session.add(other)
        await session.flush()
        session.add(
            DeliveryRunModel(
                tenant_id=ctx.tenant_id,
                branch_id=ctx.branch_id,
                delivery_route_id=ctx.route_ids[0],
                employee_id=other.id,
                status="in_transit",
            )
        )
        await session.commit()
    resp = await client.get("/delivery/me/run", headers=headers)
    assert resp.json() is None


# --- Lifecycle: depart / mark / finish --------------------------------------
async def test_depart_mark_and_finish_own_run(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    _, delivery_id = await _pending_delivery(ctx.branch_id)
    opened = await client.post("/delivery/me/run", headers=headers, json={})
    run_id = opened.json()["id"]

    departed = await client.post(
        f"/delivery/me/runs/{run_id}/depart", headers=headers
    )
    assert departed.status_code == 200
    assert departed.json()["status"] == "in_transit"
    assert departed.json()["stops"][0]["delivery_status"] == "in_transit"

    marked = await client.post(
        f"/delivery/me/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )
    assert marked.status_code == 200
    stop = marked.json()["stops"][0]
    assert stop["delivery_status"] == "delivered"
    assert stop["not_delivered_reason"] is None

    finished = await client.post(
        f"/delivery/me/runs/{run_id}/finish", headers=headers
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"


async def test_mark_not_delivered_persists_reason_and_comment(
    client: AsyncClient,
) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    _, d_reason = await _pending_delivery(ctx.branch_id, address="A")
    _, d_plain = await _pending_delivery(ctx.branch_id, address="B")
    opened = await client.post("/delivery/me/run", headers=headers, json={})
    run_id = opened.json()["id"]
    await client.post(f"/delivery/me/runs/{run_id}/depart", headers=headers)

    with_reason = await client.post(
        f"/delivery/me/deliveries/{d_reason}/mark-delivered",
        headers=headers,
        json={
            "delivered": False,
            "reason": "Cliente no contesta",
            "comment": "Timbre dañado",
        },
    )
    assert with_reason.status_code == 200
    stop = next(s for s in with_reason.json()["stops"] if s["id"] == str(d_reason))
    assert stop["delivery_status"] == "not_delivered"
    assert stop["not_delivered_reason"] == "Cliente no contesta — Timbre dañado"

    without = await client.post(
        f"/delivery/me/deliveries/{d_plain}/mark-delivered",
        headers=headers,
        json={"delivered": False},
    )
    stop2 = next(s for s in without.json()["stops"] if s["id"] == str(d_plain))
    assert stop2["not_delivered_reason"] is None


async def test_mark_delivered_rejects_unknown_reason(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    _, delivery_id = await _pending_delivery(ctx.branch_id)
    opened = await client.post("/delivery/me/run", headers=headers, json={})
    await client.post(
        f"/delivery/me/runs/{opened.json()['id']}/depart", headers=headers
    )
    resp = await client.post(
        f"/delivery/me/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "no-existe"},
    )
    assert resp.status_code == 422


# --- Unassign before departure ----------------------------------------------
async def test_unassign_returns_delivery_to_pending(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    _, delivery_id = await _pending_delivery(ctx.branch_id)
    await client.post("/delivery/me/run", headers=headers, json={})

    resp = await client.post(
        f"/delivery/me/deliveries/{delivery_id}/unassign", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["stops"] == []
    async with SessionFactory() as session:
        model = (
            await session.execute(
                select(OrderDeliveryModel).where(OrderDeliveryModel.id == delivery_id)
            )
        ).scalar_one()
        assert model.delivery_status == "pending"
        assert model.delivery_run_id is None
        assert model.delivery_route_id is None


async def test_unassign_after_departure_is_rejected(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    _, delivery_id = await _pending_delivery(ctx.branch_id)
    opened = await client.post("/delivery/me/run", headers=headers, json={})
    await client.post(
        f"/delivery/me/runs/{opened.json()['id']}/depart", headers=headers
    )
    resp = await client.post(
        f"/delivery/me/deliveries/{delivery_id}/unassign", headers=headers
    )
    assert resp.status_code == 409


# --- Ownership + permission guards ------------------------------------------
async def test_cannot_act_on_another_drivers_run(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    # Build another driver's preparing run holding one delivery.
    _, foreign_delivery = await _pending_delivery(ctx.branch_id)
    async with SessionFactory() as session:
        other = EmployeeModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            person_id=await _new_person(session),
            user_id=await _new_user(session, ctx.tenant_id),
            role_id=(
                await session.execute(select(EmployeeModel.role_id))
            ).scalars().first(),
        )
        session.add(other)
        await session.flush()
        other_run = DeliveryRunModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            delivery_route_id=ctx.route_ids[0],
            employee_id=other.id,
            status="preparing",
        )
        session.add(other_run)
        await session.flush()
        model = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.id == foreign_delivery
                )
            )
        ).scalar_one()
        model.delivery_run_id = other_run.id
        model.delivery_route_id = ctx.route_ids[0]
        model.delivery_status = "assigned"
        await session.commit()
        run_id = other_run.id

    assert (
        await client.post(f"/delivery/me/runs/{run_id}/depart", headers=headers)
    ).status_code == 404
    assert (
        await client.post(f"/delivery/me/runs/{run_id}/finish", headers=headers)
    ).status_code == 404
    assert (
        await client.post(
            f"/delivery/me/deliveries/{foreign_delivery}/unassign", headers=headers
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/delivery/me/deliveries/{foreign_delivery}/mark-delivered",
            headers=headers,
            json={"delivered": True},
        )
    ).status_code == 404


async def test_without_drive_permission_is_forbidden(client: AsyncClient) -> None:
    # A role lacking delivery.drive (waiter) — still 403 on the driver surface.
    await _make_driver(role="waiter", routes=0)
    headers = await _login(client)
    resp = await client.get("/delivery/me/run", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_drive_without_employee_link_is_not_found(client: AsyncClient) -> None:
    # Holds delivery.drive (courier) but the user is not linked to any employee.
    await _make_driver(role="courier", link_employee=False)
    headers = await _login(client)
    resp = await client.get("/delivery/me/run", headers=headers)
    assert resp.status_code == 404


# --- Fixture helpers --------------------------------------------------------
async def _new_person(session) -> uuid.UUID:  # type: ignore[no-untyped-def]
    person = PersonModel(first_name="Oth", last_name="Er")
    session.add(person)
    await session.flush()
    return person.id


async def _new_user(session, tenant_id: uuid.UUID) -> uuid.UUID:  # type: ignore[no-untyped-def]
    user = UserModel(
        tenant_id=tenant_id,
        email=f"u-{uuid.uuid4().hex[:8]}@demo.com",
        hashed_password="x",
        name="U",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user.id


async def _enriched_order(
    ctx: Ctx, *, position: int, name: str, phone: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """An order with a customer, one item (Burger x2) and a full cash payment, plus its
    pending delivery at `position`. Returns (order_id, delivery_id)."""
    async with SessionFactory() as session:
        first, _, last = name.partition(" ")
        person = PersonModel(first_name=first or name, last_name="Ruiz", phone=phone)
        session.add(person)
        await session.flush()
        customer = CustomerModel(tenant_id=ctx.tenant_id, person_id=person.id)
        session.add(customer)
        await session.flush()
        emp_id = (
            await session.execute(
                select(EmployeeModel.id).where(
                    EmployeeModel.tenant_id == ctx.tenant_id
                )
            )
        ).scalars().first()
        order = OrderModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            channel="delivery",
            employee_id=emp_id,
            customer_id=customer.id,
            status="open",
            # Cocinado: estos tests son sobre el despacho, no sobre el gate de cocina.
            kitchen_state="ready",
            total=Decimal("25000"),
        )
        session.add(order)
        await session.flush()
        # Menu chain for the item's display name.
        category = CategoryModel(tenant_id=ctx.tenant_id, name="Food")
        session.add(category)
        await session.flush()
        product = ProductModel(
            tenant_id=ctx.tenant_id, category_id=category.id, name="Burger"
        )
        session.add(product)
        await session.flush()
        variant = ProductVariantModel(tenant_id=ctx.tenant_id, product_id=product.id)
        session.add(variant)
        await session.flush()
        session.add(
            OrderItemModel(
                tenant_id=ctx.tenant_id,
                branch_id=ctx.branch_id,
                order_id=order.id,
                product_variant_id=variant.id,
                quantity=2,
                unit_price=Decimal("12500"),
                line_subtotal=Decimal("25000"),
            )
        )
        cash = CashSessionModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            opened_by_employee_id=emp_id,
            opening_amount=Decimal("0"),
            status="open",
        )
        session.add(cash)
        await session.flush()
        session.add(
            OrderPaymentModel(
                tenant_id=ctx.tenant_id,
                branch_id=ctx.branch_id,
                order_id=order.id,
                cash_session_id=cash.id,
                amount=Decimal("25000"),
                method="cash",
                employee_id=emp_id,
            )
        )
        delivery = OrderDeliveryModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            order_id=order.id,
            address_text="Calle X",
            delivery_status="pending",
            route_position=position,
        )
        session.add(delivery)
        await session.commit()
        return order.id, delivery.id
