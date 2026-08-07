"""El cliente manda su comprobante por el enlace. Y su saldo NO se mueve.

Es la prueba que sostiene la funcionalidad: si algún día declarar empezara a sumar al pagado,
un pedido entraría a cocina porque alguien subió una foto.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.main import app
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentClaimModel,
    OrderPaymentModel,
)
from restaurante.modules.storefront.infrastructure.api.deps import get_proof_store
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import SeededMenu, seed_menu, seed_primary_branch

STORED_URL = "https://cdn.test/payment-proofs/x.jpg"


@pytest.fixture(autouse=True)
def _clean_overrides() -> Any:
    """El doble de almacenamiento muere con la prueba: dejarlo puesto contaminaría las demás."""
    yield
    app.dependency_overrides.pop(get_proof_store, None)


async def _fake_store(
    tenant_id: uuid.UUID, order_id: uuid.UUID, content_type: str, data: bytes
) -> str:
    """Doble del almacenamiento: aquí se prueba la regla, no que Cloudflare conteste."""
    return STORED_URL


def _use_fake_storage() -> None:
    app.dependency_overrides[get_proof_store] = lambda: _fake_store


async def _order_by_transfer(client: AsyncClient) -> tuple[SeededMenu, str]:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price="28000.00")
    await seed_open_cash_session(branch_id)
    payload: dict[str, Any] = {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "transfer",
        "lines": [{"variantId": str(seeded.variant_id), "quantity": 1}],
    }
    resp = await client.post("/storefront/orders", json=payload)
    assert resp.status_code == 201, resp.text
    return seeded, str(resp.json()["editToken"])


def _upload(client: AsyncClient, token: str, **over: Any) -> Any:
    files = over.pop("files", {"file": ("comprobante.jpg", b"unos bytes", "image/jpeg")})
    return client.post(
        f"/storefront/orders/{token}/payment-proof",
        data={"amount": over.pop("amount", "28000")},
        files=files,
    )


async def test_sending_a_receipt_leaves_the_balance_exactly_as_it_was(
    client: AsyncClient,
) -> None:
    _use_fake_storage()
    _seeded, token = await _order_by_transfer(client)
    before = (await client.get(f"/storefront/orders/{token}")).json()

    resp = await _upload(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "pending"
    assert body["order"]["total"] == before["total"]
    assert body["order"]["outstanding"] == before["outstanding"]
    assert body["order"]["paid"] == "0.00"
    # Y la vista lo dice: hay algo esperando confirmación, que NO es lo mismo que pagado.
    assert body["order"]["paymentProofPending"] is True

    async with SessionFactory() as session:
        payments = (await session.execute(select(OrderPaymentModel))).scalars().all()
        claims = (await session.execute(select(OrderPaymentClaimModel))).scalars().all()
    assert payments == [], "una declaración no puede registrar dinero"
    assert len(claims) == 1
    assert claims[0].proof_url == STORED_URL
    assert claims[0].amount == Decimal("28000")
    # El método sale del PEDIDO, no del formulario.
    assert claims[0].method == "transfer"


async def test_the_order_reports_the_pending_proof_until_someone_looks(
    client: AsyncClient,
) -> None:
    _use_fake_storage()
    _seeded, token = await _order_by_transfer(client)
    assert (await client.get(f"/storefront/orders/{token}")).json()[
        "paymentProofPending"
    ] is False

    await _upload(client, token)

    assert (await client.get(f"/storefront/orders/{token}")).json()[
        "paymentProofPending"
    ] is True


async def test_a_dead_link_stores_nothing(client: AsyncClient) -> None:
    _use_fake_storage()
    await _order_by_transfer(client)

    resp = await _upload(client, "z" * 43)

    assert resp.status_code == 404
    async with SessionFactory() as session:
        claims = (await session.execute(select(OrderPaymentClaimModel))).scalars().all()
    assert claims == []


async def test_a_file_that_is_not_a_receipt_is_refused(client: AsyncClient) -> None:
    """Sin doble de almacenamiento: la validación de tipo ocurre antes de tocar R2."""
    _seeded, token = await _order_by_transfer(client)

    resp = await _upload(
        client, token, files={"file": ("virus.html", b"<script>", "text/html")}
    )

    assert resp.status_code == 422, resp.text
    async with SessionFactory() as session:
        claims = (await session.execute(select(OrderPaymentClaimModel))).scalars().all()
    assert claims == []


async def test_receipts_are_capped_per_order(client: AsyncClient) -> None:
    _use_fake_storage()
    _seeded, token = await _order_by_transfer(client)
    for _ in range(3):
        assert (await _upload(client, token)).status_code == 200

    resp = await _upload(client, token)

    assert resp.status_code == 409, resp.text
    async with SessionFactory() as session:
        order = (await session.execute(select(OrderModel))).scalars().first()
    assert order is not None and order.status == "open"
