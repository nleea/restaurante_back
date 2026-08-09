"""Los tres canales cobran lo mismo por el mismo plato.

Es el requisito que hace que las fórmulas no puedan volver a divergir, y hay que probarlo con los
tres caminos de verdad —no con tres llamadas a la misma función— porque lo que se rompió antes no
fue el cálculo: fue que cada camino tenía el suyo.

```
salón          POST /orders/{id}/items                    (personal, autenticado)
carta pública  POST /storefront/orders                    (anónimo)
autoservicio   PATCH del enlace de edición del cliente    (por token)
```

Y una segunda propiedad, en el mismo fichero porque es la otra cara: **un producto sin precio en la
sede se rechaza por los tres**, en vez de venderse a cero por alguno.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import ProductPriceModel
from restaurante.modules.orders.infrastructure.models import OrderItemModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_employee,
    _login,
)
from tests.modules.storefront._seed import (
    demo_tenant_id,
    seed_menu,
    seed_primary_branch,
)
from tests.modules.storefront.test_storefront_order_edit_api import _order_with_token

PRICE = "28000.00"


async def _lines_of(order_id: uuid.UUID) -> list[Decimal]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(OrderItemModel.unit_price)
                .where(OrderItemModel.order_id == order_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalars()
        return [Decimal(r) for r in rows]


async def _lines_for_token(client: AsyncClient, token: str) -> list[Decimal]:
    """Los precios de las líneas tal y como los ve el cliente en su enlace."""
    body = (await client.get(f"/storefront/orders/{token}")).json()
    return [Decimal(line["unitPrice"]) for line in body["lines"]]


async def _drop_price(branch_id: uuid.UUID) -> None:
    """Retira el precio de la sede, como si el dueño lo hubiera desactivado."""
    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(ProductPriceModel)
                .where(ProductPriceModel.branch_id == branch_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalars().first()
        assert row is not None
        row.is_active = False
        await session.commit()


async def _public_order(client: AsyncClient, seeded: object) -> object:
    return await client.post(
        "/storefront/orders",
        json={
            "customer": {"name": "Ana Pérez", "phone": "3001234567"},
            "fulfillment": {"type": "pickup"},
            "paymentMethod": "efectivo",
            "lines": [
                {"variantId": str(seeded.variant_id), "quantity": 1}  # type: ignore[attr-defined]
            ],
        },
    )


# --- El mismo número por los tres caminos ----------------------------------
async def test_the_public_channel_charges_the_catalogue_price(
    client: AsyncClient,
) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)

    resp = await _public_order(client, seeded)

    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])
    assert await _lines_of(order_id) == [Decimal(PRICE)]


async def test_staff_charges_the_same_as_the_public_channel(
    client: AsyncClient,
) -> None:
    """La prueba del requisito: dos canales, un número.

    Si algún día alguien vuelve a meter una fórmula en uno de los dos, esto se cae — que es
    exactamente para lo que está.
    """
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    employee_id = await _create_employee(
        branch_id, email=f"w{uuid.uuid4().hex[:8]}@demo.com"
    )
    await seed_open_cash_session(branch_id, employee_id)

    public = await _public_order(client, seeded)
    assert public.status_code == 201, public.text

    await _assign_role("admin")
    headers = await _login(client)
    staff_order = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "takeaway",
            "employee_id": str(employee_id),
        },
    )
    assert staff_order.status_code == 201, staff_order.text
    added = await client.post(
        f"/orders/{staff_order.json()['id']}/items",
        headers=headers,
        json={"product_variant_id": str(seeded.variant_id), "quantity": 1},
    )
    assert added.status_code == 201, added.text

    public_price = (await _lines_of(uuid.UUID(public.json()["orderId"])))[0]
    assert Decimal(added.json()["unit_price"]) == public_price == Decimal(PRICE)


# --- Y sin precio, los tres se niegan --------------------------------------
async def test_the_public_channel_refuses_an_unpriced_product(
    client: AsyncClient,
) -> None:
    """Antes lo añadía a cero: un cliente anónimo se llevaba el plato gratis y nadie lo veía."""
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    await _drop_price(branch_id)

    resp = await _public_order(client, seeded)

    assert resp.status_code == 422, resp.text
    assert "precio" in resp.text.lower()


async def test_the_public_refusal_leaves_no_half_order(
    client: AsyncClient,
) -> None:
    """El carrito se resuelve ENTERO antes de abrir la comanda, así que no queda un pedido a medias.

    Sin la comprobación previa, el rechazo llegaría dentro del bucle que añade líneas y dejaría una
    comanda abierta con parte del carrito — peor que el cero que veníamos a arreglar.
    """
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    await _drop_price(branch_id)

    await _public_order(client, seeded)

    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        count = len(
            (
                await session.execute(
                    select(OrderItemModel.id)
                    .where(OrderItemModel.tenant_id == tenant_id)
                    .execution_options(skip_tenant_filter=True)
                )
            )
            .scalars()
            .all()
        )
    assert count == 0


# --- El autoservicio: mismo cálculo, y el rechazo es de todo el lote --------
async def test_self_service_refuses_an_unpriced_line_and_writes_nothing(
    client: AsyncClient,
) -> None:
    """Un producto sin precio no entra por el enlace del cliente, y el lote entero se cae.

    Es el peor sitio para un `else Decimal(0)`: el cliente se añade el plato a su propio pedido y no
    debe nada por él, sin ningún empleado en el circuito que lo note.

    Que el rechazo sea de TODO el lote no es una elección de esta prueba: es como se comporta ya el
    resto de esta capability, y es lo que impide que un carrito quede a medias.
    """
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    token = await _order_with_token(client, seeded)
    before = await _lines_for_token(client, token)
    await _drop_price(branch_id)

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )

    assert resp.status_code == 422, resp.text
    assert "precio" in resp.text.lower()
    assert await _lines_for_token(client, token) == before


async def test_self_service_charges_the_catalogue_price(
    client: AsyncClient,
) -> None:
    """Lo que se añade por el enlace cuesta lo mismo que si lo añadiera un mesero."""
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    token = await _order_with_token(client, seeded)

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )

    assert resp.status_code == 200, resp.text
    lines = await _lines_for_token(client, token)
    assert lines == [Decimal(PRICE), Decimal(PRICE)]
