"""Una declaración del cliente NO es un pago. Es lo único que estas pruebas cuidan.

Si algún día alguien mueve las declaraciones a `order_payments` "para simplificar", estas
pruebas caen — y caen por el sitio correcto: un pedido entrando a cocina porque alguien escribió
que ya pagó.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.orders.application.use_cases.manage_payments import (
    MAX_PENDING_CLAIMS,
    PaymentService,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ConflictError, ValidationError
from tests.modules.orders.test_payment_verification import (
    _ids,
    _login,
    _payments_of,
    _setup,
)


def _service(session: object, notifier: object | None = None) -> PaymentService:
    return PaymentService(
        repo=SqlAlchemyOrdersRepository(session),  # type: ignore[arg-type]
        customer_notifier=notifier,  # type: ignore[arg-type]
    )


async def _declare(
    order_id: uuid.UUID, amount: str = "25000", proof: str | None = "https://r2/x.jpg"
) -> object:
    tenant_id, _ = await _ids()
    async with SessionFactory() as session:
        return await _service(session).declare_payment(
            tenant_id, order_id, Decimal(amount), "transfer", proof
        )


async def _order(order_id: uuid.UUID) -> OrderModel:
    async with SessionFactory() as session:
        return (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()


# --- Lo que una declaración NO hace ------------------------------------------
async def test_declaring_moves_no_money_and_changes_no_state(
    client: AsyncClient,
) -> None:
    order_id, _employee = await _setup("transfer")
    before = await _order(order_id)
    before_state = (before.status, before.kitchen_state, before.total)

    await _declare(order_id)

    assert await _payments_of(order_id) == [], "una declaración no puede registrar dinero"
    after = await _order(order_id)
    assert (after.status, after.kitchen_state, after.total) == before_state


async def test_a_declared_order_still_cannot_reach_the_kitchen(
    client: AsyncClient,
) -> None:
    """La prueba que sostiene el diseño entero: el cliente dice que pagó y NO se cocina."""
    headers = await _login(client)
    order_id, _employee = await _setup("transfer")
    await _declare(order_id)

    resp = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)

    assert resp.status_code == 409, resp.text
    assert "verific" in resp.json()["detail"].lower()


async def test_pending_claims_are_capped(client: AsyncClient) -> None:
    order_id, _employee = await _setup("transfer")
    for _ in range(MAX_PENDING_CLAIMS):
        await _declare(order_id)

    with pytest.raises(ConflictError):
        await _declare(order_id)


async def test_a_non_positive_declaration_is_refused(client: AsyncClient) -> None:
    order_id, _employee = await _setup("transfer")
    with pytest.raises(ValidationError):
        await _declare(order_id, amount="0")


# --- Resolver -----------------------------------------------------------------
async def test_verifying_accepts_the_pending_claims(client: AsyncClient) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")
    await _declare(order_id)

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert resp.status_code == 200, resp.text

    tenant_id, _ = await _ids()
    async with SessionFactory() as session:
        claims = await _service(session).list_payment_claims(tenant_id, order_id)
    assert [c.status for c in claims] == ["accepted"]
    assert claims[0].resolved_by_employee_id == employee_id


async def test_verifying_without_any_claim_still_works(client: AsyncClient) -> None:
    """La declaración ayuda a decidir; no es un requisito para cobrar."""
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")

    resp = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )

    assert resp.status_code == 200, resp.text
    assert len(await _payments_of(order_id)) == 1


async def test_rejecting_registers_nothing_and_leaves_the_door_open(
    client: AsyncClient,
) -> None:
    order_id, employee_id = await _setup("transfer")
    claim = await _declare(order_id)
    tenant_id, _ = await _ids()

    async with SessionFactory() as session:
        rejected = await _service(session).reject_payment_claim(
            tenant_id,
            order_id,
            claim.id,  # type: ignore[attr-defined]
            "El comprobante es de otro pedido",
            employee_id,
        )

    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "El comprobante es de otro pedido"
    assert await _payments_of(order_id) == []
    # Y el cliente puede volver a mandar uno: el rechazo no cierra la puerta.
    await _declare(order_id)


async def test_a_rejection_needs_a_reason(client: AsyncClient) -> None:
    order_id, employee_id = await _setup("transfer")
    claim = await _declare(order_id)
    tenant_id, _ = await _ids()

    async with SessionFactory() as session:
        with pytest.raises(ValidationError):
            await _service(session).reject_payment_claim(
                tenant_id, order_id, claim.id, "   ", employee_id  # type: ignore[attr-defined]
            )


# --- El caso que originó todo -------------------------------------------------
async def test_a_total_that_grows_after_verification_charges_only_the_difference(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    order_id, employee_id = await _setup("transfer")

    first = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert first.status_code == 200, first.text

    # El cliente añade algo desde su enlace y el pedido sube 2.500.
    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        order.total = Decimal("27500")
        await session.commit()

    await _declare(order_id, amount="2500")
    second = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert second.status_code == 200, second.text

    amounts = sorted(p.amount for p in await _payments_of(order_id))
    assert amounts == [Decimal("2500"), Decimal("25000")], "el primer pago no se toca"


async def test_verifying_notifies_the_customer_once_no_matter_how_many_claims(
    client: AsyncClient,
) -> None:
    """Que le confirmen el pago es UN hecho para el cliente. Cuántas veces lo declaró es
    contabilidad nuestra.

    Dos declaraciones por un solo pago no es un caso raro, es el camino normal: dice "ya pagué"
    desde el enlace de pago —sin adjuntar nada— y después manda la foto por WhatsApp, que alguien
    reclama desde el chat. Avisar por declaración le mandaba el mismo mensaje dos veces.
    """
    tenant_id, _ = await _ids()
    order_id, employee_id = await _setup("transfer")
    # El "ya pagué" del enlace (sin soporte) y el comprobante que llegó por el chat.
    await _declare(order_id, amount="25000", proof=None)
    await _declare(order_id, amount="25000", proof="https://r2/comprobante.jpg")

    sent: list[tuple[uuid.UUID, str]] = []

    class RecordingNotifier:
        async def notify_payment_claim(
            self,
            tenant_id: uuid.UUID,
            order_id: uuid.UUID,
            status: str,
            reason: str | None,
        ) -> None:
            sent.append((order_id, status))

    async with SessionFactory() as session:
        await _service(session, notifier=RecordingNotifier()).verify_payment(
            tenant_id, order_id, employee_id
        )

    assert sent == [(order_id, "accepted")], (
        f"el cliente recibió {len(sent)} avisos por un solo pago confirmado"
    )
    # Y las DOS declaraciones quedan aceptadas: no se avisa dos veces, pero tampoco se deja
    # ninguna colgando en `pending`.
    async with SessionFactory() as session:
        claims = await _service(session).list_payment_claims(tenant_id, order_id)
    assert [c.status for c in claims] == ["accepted", "accepted"]
