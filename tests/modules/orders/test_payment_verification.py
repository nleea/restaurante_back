"""No se cocina un prepago sin confirmar, y verificar es un solo gesto.

El caso real: el cliente pide por el storefront y paga por Nequi. Alguien mira el comprobante
y dice "ok" — ese ok tiene que registrar el cobro Y mandar a cocina, porque para quien atiende
es el mismo momento. Separarlos crea el estado "verificado pero sin cocinar" que nadie mira.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _ids() -> tuple[uuid.UUID, uuid.UUID]:
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
    tenant_id, user_id = await _ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _setup(
    payment_method: str, *, with_cash_session: bool = True
) -> tuple[uuid.UUID, uuid.UUID]:
    """Un pedido de domicilio abierto, sin enrutar, con su empleado. Devuelve (order, employee)."""
    tenant_id, user_id = await _ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="centro", name="Centro", is_active=True
        )
        session.add(branch)
        await session.flush()
        person = PersonModel(first_name="Ana", last_name="Restrepo")
        session.add(person)
        await session.flush()
        # El rol del empleado no importa aquí: lo que se prueba es el dinero, no su RBAC.
        roles = await seed_rbac(session)
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            person_id=person.id,
            user_id=user_id,
            role_id=roles["admin"].id,
            is_active=True,
        )
        session.add(employee)
        await session.flush()
        if with_cash_session:
            session.add(
                CashSessionModel(
                    tenant_id=tenant_id,
                    branch_id=branch.id,
                    opened_by_employee_id=employee.id,
                    opening_amount=Decimal("0"),
                    status="open",
                )
            )
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            channel="delivery",
            employee_id=employee.id,
            status="open",
            total=Decimal("25000"),
            payment_method=payment_method,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        await session.refresh(employee)
        return order.id, employee.id


async def _payments_of(order_id: uuid.UUID) -> list[OrderPaymentModel]:
    async with SessionFactory() as session:
        rows = await session.execute(
            select(OrderPaymentModel).where(OrderPaymentModel.order_id == order_id)
        )
        return list(rows.scalars())


# --- El gate ----------------------------------------------------------------
async def test_an_unverified_prepaid_order_is_not_routed(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, _employee = await _setup("transfer")

    resp = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)

    assert resp.status_code == 409, resp.text
    assert "verific" in resp.json()["detail"].lower()


async def test_a_cash_order_routes_without_any_payment(client: AsyncClient) -> None:
    """El efectivo pasa siempre: su plata llega en la puerta."""
    headers = await _login(client)
    order_id, _employee = await _setup("cash")

    resp = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)

    assert resp.status_code == 201, resp.text
    assert await _payments_of(order_id) == []


async def test_a_verified_prepaid_order_routes_normally(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")

    verified = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert verified.status_code == 200, verified.text

    resp = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert resp.status_code == 201, resp.text


# --- Verificar ---------------------------------------------------------------
async def test_verifying_registers_the_outstanding_amount_with_the_orders_method(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 200, resp.text
    payments = await _payments_of(order_id)
    assert len(payments) == 1
    assert payments[0].amount == Decimal("25000")
    # El método sale del pedido, no de lo que alguien teclee.
    assert payments[0].method == "transfer"


async def test_verifying_twice_does_not_charge_twice(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")
    body = {"employee_id": str(employee_id)}

    first = await client.post(
        f"/orders/{order_id}/verify-payment", headers=headers, json=body
    )
    second = await client.post(
        f"/orders/{order_id}/verify-payment", headers=headers, json=body
    )

    assert first.status_code == 200
    # Idempotente a propósito: si el enrutado falló tras cobrar, reintentar es la reparación.
    assert second.status_code == 200, second.text
    assert len(await _payments_of(order_id)) == 1


async def test_verifying_a_cash_order_is_refused(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("cash")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 422, resp.text
    assert "efectivo" in resp.json()["detail"].lower()


async def test_without_an_open_cash_session_nothing_happens(
    client: AsyncClient,
) -> None:
    """Si el cobro no se puede registrar, el pedido no queda ni pagado ni cocinándose."""
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer", with_cash_session=False)

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 409, resp.text
    assert await _payments_of(order_id) == []
    # Y sigue sin poder ir a cocina.
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 409


# --- La puerta del domicilio ------------------------------------------------
# Un domicilio se crea ANTES de que exista su tarifa — eso es todo el diseño de la cotización
# diferida. En esa ventana `orders.total` es sólo la comida, así que verificar cobraría de menos
# Y abriría la cocina, y para cuando alguien lo nota el pedido va de camino.
async def _attach_delivery(order_id: uuid.UUID, quote_status: str) -> None:
    from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        session.add(
            OrderDeliveryModel(
                tenant_id=order.tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                address_text="Calle 1 #2-3",
                quote_status=quote_status,
                quote_failure_reason=(
                    "La sucursal no tiene bandas de tarifa configuradas."
                    if quote_status == "unquotable"
                    else None
                ),
            )
        )
        await session.commit()


async def test_an_unquoted_delivery_cannot_be_verified(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")
    await _attach_delivery(order_id, "pending_quote")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 409, resp.text
    assert "domicilio" in resp.json()["detail"].lower()
    # Ni dinero ni cocina: las dos cosas que verificar dispara.
    assert await _payments_of(order_id) == []
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 409


async def test_an_unquotable_delivery_says_why(client: AsyncClient) -> None:
    """El mensaje lo lee una persona con el cliente delante: tiene que saber qué arreglar."""
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")
    await _attach_delivery(order_id, "unquotable")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 409, resp.text
    assert "bandas de tarifa" in resp.json()["detail"]


async def test_a_quoted_delivery_verifies_and_charges_the_whole_total(
    client: AsyncClient,
) -> None:
    """Con la tarifa ya congelada en el total, se cobra el total — domicilio incluido."""
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")
    await _attach_delivery(order_id, "quoted")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 200, resp.text
    payments = await _payments_of(order_id)
    assert len(payments) == 1
    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
    assert payments[0].amount == order.total
