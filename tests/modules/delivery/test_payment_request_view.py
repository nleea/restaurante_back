"""La página de pago: qué ve el cliente y, sobre todo, qué se le cobra.

El error que estos tests existen para impedir es de una cifra: cobrar el DOMICILIO en vez del
TOTAL. Un enlace que pide $6.000 por un pedido de $38.000 se paga, se marca como pagado, y la
diferencia aparece en la puerta con la comida ya entregada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.delivery.infrastructure.models import (
    DeliveryPaymentRequestModel,
    OrderDeliveryModel,
)
from restaurante.modules.delivery.infrastructure.payment_requests import (
    issue_payment_token,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    seed_delivery_ready,
    seed_menu,
    seed_primary_branch,
)

_SUBTOTAL = Decimal("32000")
_FEE = Decimal("6000")
_TOTAL = _SUBTOTAL + _FEE


async def _quoted_delivery_with_link(client: AsyncClient) -> str:
    """Un domicilio ya cotizado y su enlace de pago vivo. Devuelve el token en claro.

    El pedido se crea por el API público de verdad —sin método de pago, como ahora nacen los
    domicilios— y luego se le aplica la cotización a mano, que es lo que hace el worker.
    """
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    resp = await client.post(
        "/storefront/orders",
        json={
            "customer": {"name": "Ana Pérez", "phone": "3001234567"},
            "fulfillment": {
                "type": "delivery",
                "addressText": "Calle 1 #2-3",
                "latitude": 11.55,
                "longitude": -72.90,
            },
            "lines": [{"variantId": str(seeded.variant_id), "quantity": 2}],
        },
    )
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])

    async with SessionFactory() as s:
        order = (
            await s.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        # Lo que el cotizador escribe: la tarifa congelada Y el total recalculado, juntos.
        order.delivery_fee = _FEE
        order.total = order.subtotal - order.discount + _FEE
        delivery = (
            await s.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.order_id == order_id
                )
            )
        ).scalar_one()
        delivery.quote_status = "quoted"
        delivery.quote_distance_km = Decimal("2.400")
        delivery.quoted_fee = _FEE

        raw, token_hash = issue_payment_token()
        s.add(
            DeliveryPaymentRequestModel(
                tenant_id=order.tenant_id,
                branch_id=order.branch_id,
                order_id=order.id,
                order_delivery_id=delivery.id,
                token_hash=token_hash,
                quote_distance_km=Decimal("2.400"),
                quoted_fee=_FEE,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        await s.commit()
        return raw


async def test_the_page_breaks_the_total_down(client: AsyncClient) -> None:
    token = await _quoted_delivery_with_link(client)

    resp = await client.get(f"/delivery/payment-requests/{token}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # LA cifra: lo que se pide pagar es el total, no el cargo de domicilio.
    subtotal = Decimal(str(body["subtotal"]))
    assert Decimal(str(body["delivery_fee"])) == _FEE
    assert Decimal(str(body["total"])) == subtotal + _FEE
    assert Decimal(str(body["amount_due"])) == subtotal + _FEE
    assert Decimal(str(body["amount_due"])) != _FEE, "cobrar el domicilio en vez del total"
    # Y desglosado, para que el cliente pueda comprobarlo sin preguntar.
    assert len(body["lines"]) == 1
    assert body["lines"][0]["quantity"] == 2
    assert Decimal(str(body["lines"][0]["line_subtotal"])) == subtotal
    assert body["order_code"]
    assert body["address_text"] == "Calle 1 #2-3"


async def test_the_figures_add_up(client: AsyncClient) -> None:
    """subtotal − descuento + domicilio = total. Si esto falla, el cliente ve una resta rota."""
    token = await _quoted_delivery_with_link(client)

    body = (await client.get(f"/delivery/payment-requests/{token}")).json()

    assert (
        Decimal(str(body["subtotal"]))
        - Decimal(str(body["discount"]))
        + Decimal(str(body["delivery_fee"]))
        == Decimal(str(body["total"]))
    )


async def test_an_unknown_token_reveals_nothing(client: AsyncClient) -> None:
    resp = await client.get(f"/delivery/payment-requests/{uuid.uuid4().hex}")

    assert resp.status_code == 404
    assert "order_code" not in resp.text


# --- Reemitir el enlace -------------------------------------------------------
# No es reenviar: del enlace anterior sólo se guardó su hash, así que no existe en ninguna parte.
# Esto acuña uno NUEVO sobre la MISMA cotización congelada e invalida el anterior.
async def _login(client: AsyncClient) -> dict[str, str]:
    """Un admin de verdad: reemitir exige `delivery.assign`, que manda un total a un cliente."""
    from scripts.seed import seed_rbac
    from sqlalchemy import select as sa_select

    from restaurante.modules.identity.infrastructure.models import UserModel
    from restaurante.modules.identity.infrastructure.repositories import (
        SqlAlchemyRbacRepository,
    )
    from restaurante.shared.tenancy.models import TenantModel
    from tests.conftest import TEST_EMAIL, TEST_PASSWORD

    async with SessionFactory() as session:
        tenant_id = (
            await session.execute(
                sa_select(TenantModel.id).where(TenantModel.slug == "demo")
            )
        ).scalar_one()
        user_id = (
            await session.execute(
                sa_select(UserModel.id).where(UserModel.email == TEST_EMAIL)
            )
        ).scalar_one()
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )
        await session.commit()

    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _delivery_id(order_code_token: str) -> uuid.UUID:
    async with SessionFactory() as s:
        return (
            await s.execute(select(OrderDeliveryModel.id).limit(1))
        ).scalars().one()


async def test_reissuing_mints_a_new_link_and_kills_the_old_one(
    client: AsyncClient,
) -> None:
    token = await _quoted_delivery_with_link(client)
    headers = await _login(client)
    delivery_id = await _delivery_id(token)

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/payment-request", headers=headers
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # La cotización NO se recalcula: el cliente ve el mismo total que ya se le dijo.
    assert Decimal(str(body["quoted_fee"])) == _FEE
    # Y el enlace viejo deja de servir en el mismo gesto: dos enlaces vivos son dos totales.
    stale = await client.get(f"/delivery/payment-requests/{token}")
    assert stale.status_code == 404


async def test_the_reissue_response_never_carries_the_link(
    client: AsyncClient,
) -> None:
    """El enlace sale por WhatsApp, no por el API.

    Devolverlo aquí lo dejaría en el historial del navegador de un empleado y convertiría una
    pantalla de despacho en una forma de cobrarle a un cliente por fuera.
    """
    await _quoted_delivery_with_link(client)
    headers = await _login(client)
    delivery_id = await _delivery_id("")

    body = (
        await client.post(
            f"/delivery/deliveries/{delivery_id}/payment-request", headers=headers
        )
    ).json()

    assert "token" not in str(body)
    assert "payment/delivery" not in str(body)


async def test_an_unquoted_delivery_cannot_be_reissued(client: AsyncClient) -> None:
    """No hay nada que reenviar: sin cotización no existe enlace ni total."""
    await _quoted_delivery_with_link(client)
    headers = await _login(client)
    delivery_id = await _delivery_id("")
    async with SessionFactory() as s:
        delivery = (
            await s.execute(
                select(OrderDeliveryModel).where(OrderDeliveryModel.id == delivery_id)
            )
        ).scalar_one()
        delivery.quote_status = "pending_quote"
        delivery.quoted_fee = None
        await s.commit()

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/payment-request", headers=headers
    )

    assert resp.status_code == 422, resp.text
    assert "cotizada" in resp.json()["detail"].lower()
