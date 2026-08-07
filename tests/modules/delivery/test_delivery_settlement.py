"""Resolver una entrega cierra su comanda — en los dos desenlaces.

El bug que esto cierra: `mark_delivered` cambiaba un estado y nada más. Un domicilio entregado
seguía apareciendo en Salón esperando un cobro que ya nadie iba a hacer.

Y el write-off: el cliente que no recibió nada no puede quedar debiéndolo. Pero el inventario
sí se descuenta, porque la comida se cocinó igual.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.customers.infrastructure.models import (
    CustomerCreditModel,
    CustomerModel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from tests.modules.delivery.test_delivery_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_order,
    _create_route,
    _demo_ids,
    _login,
)


async def _open_cash(branch_id: uuid.UUID, employee_id: uuid.UUID) -> None:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        session.add(
            CashSessionModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                opened_by_employee_id=employee_id,
                opening_amount=Decimal("0"),
                status="open",
            )
        )
        await session.commit()


async def _order_of(order_id: uuid.UUID) -> OrderModel:
    async with SessionFactory() as session:
        return (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()


async def _in_transit(
    client: AsyncClient,
    *,
    payment_method: str = "cash",
    total: Decimal = Decimal("25000"),
    with_customer: bool = False,
    open_cash: bool = True,
) -> tuple[dict[str, str], str, uuid.UUID, uuid.UUID]:
    """Una entrega en camino. Devuelve (headers, delivery_id, order_id, branch_id)."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, f"set-{uuid.uuid4().hex[:6]}@demo.com")
    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    if open_cash:
        await _open_cash(branch_id, driver)
    order_id = await _create_order(branch_id, driver)

    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        order.total = total
        order.payment_method = payment_method
        if with_customer:
            person = PersonModel(first_name="Ana", last_name="Cliente")
            session.add(person)
            await session.flush()
            customer = CustomerModel(tenant_id=tenant_id, person_id=person.id)
            session.add(customer)
            await session.flush()
            order.customer_id = customer.id
        await session.commit()

    run_id = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_id, "employee_id": str(driver)},
        )
    ).json()["id"]
    delivery_id = (
        await client.post(
            "/delivery/deliveries",
            headers=headers,
            json={"order_id": str(order_id), "address_text": "Calle 9"},
        )
    ).json()["id"]
    await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )
    await client.post(f"/delivery/runs/{run_id}/depart", headers=headers)
    return headers, delivery_id, order_id, branch_id


# --- Entregada ---------------------------------------------------------------
async def test_a_prepaid_delivery_closes_its_order(client: AsyncClient) -> None:
    headers, delivery_id, order_id, branch_id = await _in_transit(
        client, payment_method="transfer"
    )
    # Ya pagada por transferencia antes de cocinar (lo que haría "verificar el pago").
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        cash_session_id = (
            await session.execute(select(CashSessionModel.id))
        ).scalars().first()
        employee_id = (
            await session.execute(select(EmployeeModel.id))
        ).scalars().first()
        session.add(
            OrderPaymentModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order_id,
                cash_session_id=cash_session_id,
                amount=Decimal("25000"),
                method="transfer",
                employee_id=employee_id,
            )
        )
        await session.commit()

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )

    assert resp.status_code == 200, resp.text
    order = await _order_of(order_id)
    assert order.status == "closed"
    assert order.closed_at is not None


async def test_a_cash_delivery_collects_and_closes_in_one_go(
    client: AsyncClient,
) -> None:
    headers, delivery_id, order_id, _branch = await _in_transit(
        client, payment_method="cash"
    )

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )

    assert resp.status_code == 200, resp.text
    async with SessionFactory() as session:
        payments = list(
            (
                await session.execute(
                    select(OrderPaymentModel).where(
                        OrderPaymentModel.order_id == order_id
                    )
                )
            ).scalars()
        )
    assert len(payments) == 1
    assert payments[0].amount == Decimal("25000")
    assert payments[0].method == "cash"
    assert (await _order_of(order_id)).status == "closed"


async def test_a_failed_collection_leaves_everything_open(
    client: AsyncClient,
) -> None:
    """Sin caja abierta no se puede cobrar — y entonces tampoco se marca entregado."""
    headers, delivery_id, order_id, branch_id = await _in_transit(
        client, payment_method="cash", open_cash=False
    )

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )

    assert resp.status_code == 409, resp.text
    assert (await _order_of(order_id)).status == "open"
    listed = await client.get(
        "/delivery/deliveries", headers=headers, params={"branch_id": str(branch_id)}
    )
    row = next(d for d in listed.json() if d["id"] == delivery_id)
    # No quedó marcada como entregada: el domiciliario no puede creer que cerró algo
    # que no cobró.
    assert row["delivery_status"] == "in_transit"


# --- No entregada: write-off -------------------------------------------------
async def test_an_undelivered_order_closes_without_charging_the_customer(
    client: AsyncClient,
) -> None:
    headers, delivery_id, order_id, _branch = await _in_transit(
        client, payment_method="cash", with_customer=True
    )

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente no contesta"},
    )

    assert resp.status_code == 200, resp.text
    order = await _order_of(order_id)
    assert order.status == "closed"

    async with SessionFactory() as session:
        credits = list(
            (await session.execute(select(CustomerCreditModel))).scalars()
        )
    # Lo impagado lo absorbe el negocio. Fiárselo convertiría una entrega fallida en una
    # deuda del cliente por comida que nunca recibió.
    assert credits == []


async def test_an_undelivered_order_still_deducts_what_was_cooked(
    client: AsyncClient,
) -> None:
    """Cerrar es el único momento en que se descuenta inventario, y la comida se cocinó."""
    headers, delivery_id, order_id, _branch = await _in_transit(client)

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente canceló"},
    )

    assert resp.status_code == 200, resp.text
    # El pedido no se queda abierto para siempre haciendo que la despensa reporte
    # stock que ya no existe.
    assert (await _order_of(order_id)).status == "closed"


async def test_the_write_off_is_derivable_afterwards(client: AsyncClient) -> None:
    headers, delivery_id, order_id, _branch = await _in_transit(client)
    await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente canceló"},
    )

    order = await _order_of(order_id)
    async with SessionFactory() as session:
        paid = list(
            (
                await session.execute(
                    select(OrderPaymentModel).where(
                        OrderPaymentModel.order_id == order_id
                    )
                )
            ).scalars()
        )
    # cerrado + no entregado + total > pagado ES la merma. Sin tabla dedicada.
    assert order.status == "closed"
    assert paid == []
    assert order.total == Decimal("25000")


async def test_no_cash_movement_is_invented_for_an_undelivered_order(
    client: AsyncClient,
) -> None:
    headers, delivery_id, _order_id, _branch = await _in_transit(client)

    await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente canceló"},
    )

    async with SessionFactory() as session:
        movements = list(
            (await session.execute(select(CashMovementModel))).scalars()
        )
    # No se cobró nada, así que nada entró ni salió del cajón.
    assert movements == []


# --- La invariante vieja sigue en pie ----------------------------------------
async def test_an_ordinary_unpaid_close_still_requires_payment_or_fiado(
    client: AsyncClient,
) -> None:
    """El write-off es exclusivo de la entrega no resuelta; no relaja el cierre normal."""
    headers, _delivery_id, order_id, _branch = await _in_transit(client)

    resp = await client.post(f"/orders/{order_id}/close", headers=headers)

    assert resp.status_code == 422, resp.text
    assert "no está pagada" in resp.json()["detail"]
    assert (await _order_of(order_id)).status == "open"
