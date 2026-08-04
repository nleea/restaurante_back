"""Devoluciones: la plata vuelve por donde entró, y el cajón ni se entera.

La trampa que esto evita: registrar la devolución de una transferencia como salida en
efectivo. El arqueo sólo cuenta `cash`, así que eso haría que el sistema esperara MENOS
plata en el cajón de la que hay — rompería el arqueo justo al intentar cuadrarlo.

Simetría que confirma el modelo: el efectivo nunca genera devoluciones. Si el cliente paga
al recibir y no recibió, no pagó.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.cash.application.use_cases.manage_cash import CashService
from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.cash.infrastructure.repositories import (
    SqlAlchemyCashRepository,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderPaymentModel,
    OrderRefundModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from tests.modules.delivery.test_delivery_api import _demo_ids
from tests.modules.delivery.test_delivery_settlement import _in_transit


async def _refunds() -> list[OrderRefundModel]:
    async with SessionFactory() as session:
        return list(
            (await session.execute(select(OrderRefundModel))).scalars()
        )


async def _movements() -> list[CashMovementModel]:
    async with SessionFactory() as session:
        return list((await session.execute(select(CashMovementModel))).scalars())


async def _an_employee() -> uuid.UUID:
    async with SessionFactory() as session:
        return (await session.execute(select(EmployeeModel.id))).scalars().first()


async def _prepaid_not_delivered(
    client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Un prepago por transferencia que no se entregó. Devuelve (headers, branch, session)."""
    headers, delivery_id, order_id, branch_id = await _in_transit(
        client, payment_method="transfer"
    )
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        cash_session_id = (
            await session.execute(select(CashSessionModel.id))
        ).scalars().first()
        session.add(
            OrderPaymentModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order_id,
                cash_session_id=cash_session_id,
                amount=Decimal("25000"),
                method="transfer",
                employee_id=await _an_employee(),
            )
        )
        await session.commit()

    await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente no contesta"},
    )
    return headers, branch_id, cash_session_id


# --- Nacimiento --------------------------------------------------------------
async def test_a_prepaid_undelivered_order_owes_a_refund(client: AsyncClient) -> None:
    await _prepaid_not_delivered(client)

    refunds = await _refunds()
    assert len(refunds) == 1
    assert refunds[0].amount == Decimal("25000")
    # Por el método por el que ENTRÓ, que es por el que tiene que salir.
    assert refunds[0].method == "transfer"
    assert refunds[0].status == "pending"


async def test_a_cash_undelivered_order_owes_nothing(client: AsyncClient) -> None:
    """El efectivo se cobra en la puerta: si no recibió, no pagó."""
    headers, delivery_id, _order_id, _branch = await _in_transit(
        client, payment_method="cash"
    )

    await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": False, "reason": "Cliente no contesta"},
    )

    assert await _refunds() == []


# --- Confirmar ---------------------------------------------------------------
async def test_confirming_a_transfer_refund_does_not_move_the_drawer(
    client: AsyncClient,
) -> None:
    """El test que importa: el arqueo físico no se altera."""
    headers, branch_id, session_id = await _prepaid_not_delivered(client)
    tenant_id, _ = await _demo_ids()
    refund_id = (await _refunds())[0].id

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        before_in, before_out = await SqlAlchemyCashRepository(session).cash_totals(
            tenant_id, session_id
        )

    resp = await client.post(
        f"/refunds/{refund_id}/confirm",
        headers=headers,
        json={"employee_id": str(await _an_employee())},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"

    async with SessionFactory() as session:
        after_in, after_out = await SqlAlchemyCashRepository(session).cash_totals(
            tenant_id, session_id
        )
    # Esa plata nunca estuvo en el cajón, así que salir de él no puede alterarlo.
    assert (after_in, after_out) == (before_in, before_out)

    # Pero el libro de caja SÍ registra la salida, con su método.
    out = [m for m in await _movements() if m.type == "out"]
    assert len(out) == 1
    assert out[0].method == "transfer"
    assert out[0].amount == Decimal("25000")
    assert out[0].concept == "refund"
    assert cash is not None


async def test_confirming_records_who_authorized_it(client: AsyncClient) -> None:
    headers, _branch, _session = await _prepaid_not_delivered(client)
    refund_id = (await _refunds())[0].id
    employee_id = await _an_employee()

    await client.post(
        f"/refunds/{refund_id}/confirm",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    refund = (await _refunds())[0]
    # "Quién autorizó esta devolución" es la pregunta del dueño el día que aparece una
    # que nadie recuerda.
    assert refund.resolved_by_employee_id == employee_id
    assert refund.resolved_at is not None


async def test_confirming_twice_is_a_conflict(client: AsyncClient) -> None:
    headers, _branch, _session = await _prepaid_not_delivered(client)
    refund_id = (await _refunds())[0].id
    body = {"employee_id": str(await _an_employee())}

    first = await client.post(f"/refunds/{refund_id}/confirm", headers=headers, json=body)
    second = await client.post(
        f"/refunds/{refund_id}/confirm", headers=headers, json=body
    )

    assert first.status_code == 200
    assert second.status_code == 409, second.text
    # Y no se creó un segundo movimiento.
    assert len([m for m in await _movements() if m.type == "out"]) == 1


# --- Cancelar ----------------------------------------------------------------
async def test_cancelling_closes_the_debt_without_moving_money(
    client: AsyncClient,
) -> None:
    headers, _branch, _session = await _prepaid_not_delivered(client)
    refund_id = (await _refunds())[0].id

    resp = await client.post(
        f"/refunds/{refund_id}/cancel",
        headers=headers,
        json={
            "employee_id": str(await _an_employee()),
            "reason": "El cliente aceptó que se le reenviara mañana",
        },
    )

    assert resp.status_code == 200, resp.text
    refund = (await _refunds())[0]
    assert refund.status == "cancelled"
    assert "reenviara" in (refund.reason or "")
    assert [m for m in await _movements() if m.type == "out"] == []


async def test_cancelling_without_a_reason_is_refused(client: AsyncClient) -> None:
    headers, _branch, _session = await _prepaid_not_delivered(client)
    refund_id = (await _refunds())[0].id

    resp = await client.post(
        f"/refunds/{refund_id}/cancel",
        headers=headers,
        json={"employee_id": str(await _an_employee()), "reason": ""},
    )

    assert resp.status_code == 422, resp.text


# --- Listado y caja ----------------------------------------------------------
async def test_a_pending_refund_survives_the_shift_close(client: AsyncClient) -> None:
    """La deuda no desaparece porque el turno cambie."""
    headers, branch_id, session_id = await _prepaid_not_delivered(client)
    tenant_id, _ = await _demo_ids()

    # La entrega quedó resuelta (not_delivered), así que la caja SÍ puede cerrar.
    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        closed = await cash.close_session(
            tenant_id, session_id, await _an_employee(), counted_amount=Decimal("0")
        )
    assert closed.status == "closed"

    listed = await client.get(
        "/refunds", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["status"] == "pending"


async def test_a_pending_refund_does_not_block_the_close(client: AsyncClient) -> None:
    """La plata está en el banco, no en el cajón: el arqueo cuadra igual."""
    _headers, _branch, session_id = await _prepaid_not_delivered(client)
    tenant_id, _ = await _demo_ids()
    assert len(await _refunds()) == 1

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        closed = await cash.close_session(
            tenant_id, session_id, await _an_employee(), counted_amount=Decimal("0")
        )

    assert closed.status == "closed"
