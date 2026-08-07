"""La API de cuentas de mesa y la impresión de su tirilla.

Aquí se protege lo que se expone: qué permisos hacen falta, qué error sale cuando algo no se
puede, y que una impresión de cuenta no manche la auditoría de sus comandas.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.modules.orders.test_orders_api import _assign_role, _login
from tests.modules.orders.test_table_bills import _seed


async def _open_bill(client: AsyncClient, headers: dict[str, str], s) -> dict:
    resp = await client.post(
        "/orders/table-bills",
        headers=headers,
        json={
            "dining_table_id": str(s.table_id),
            "employee_id": str(s.employee_id),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Abrir y leer -------------------------------------------------------------
async def test_opening_returns_every_member_with_what_it_owes(
    client: AsyncClient,
) -> None:
    s = await _seed(client, ["32000", "54000", "34000"])
    headers = await _login(client)

    body = await _open_bill(client, headers, s)

    assert body["status"] == "open"
    assert len(body["members"]) == 3
    assert body["outstanding"] == "120000.00"
    # Cada miembro trae su etiqueta: con dos "Ana" en la mesa, es lo que desempata.
    assert all(m["order_label"] for m in body["members"])


async def test_reading_a_bill_reflects_what_is_still_owed(client: AsyncClient) -> None:
    s = await _seed(client, ["32000", "54000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)

    await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [{"amount": "40000", "method": "cash"}],
            "employee_id": str(s.employee_id),
        },
    )
    body = (await client.get(f"/orders/table-bills/{bill['id']}", headers=headers)).json()

    assert body["status"] == "open"
    assert body["outstanding"] == "46000.00"
    # LA propiedad que distingue cascada de prorrata: a lo sumo UNA comanda queda a medias.
    # La prorrata dejaría a las dos parcialmente pagadas. No se afirma CUÁL queda a medias:
    # con `created_at` empatados el desempate es por `id`, estable dentro de una ejecución
    # pero no predecible desde el test.
    partial = [
        m
        for m in body["members"]
        if m["paid"] != "0.00" and m["outstanding"] != "0.00"
    ]
    assert len(partial) <= 1


# --- Cobrar -------------------------------------------------------------------
async def test_charging_in_full_settles_and_closes(client: AsyncClient) -> None:
    s = await _seed(client, ["32000", "54000", "34000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)

    resp = await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [{"amount": "120000", "method": "cash"}],
            "employee_id": str(s.employee_id),
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "settled"
    assert resp.json()["outstanding"] == "0.00"
    for order_id in s.order_ids:
        got = await client.get(f"/orders/{order_id}", headers=headers)
        assert got.json()["status"] == "closed"


async def test_a_settled_bill_conflicts_on_a_second_charge(
    client: AsyncClient,
) -> None:
    s = await _seed(client, ["32000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)
    await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [{"amount": "32000", "method": "cash"}],
            "employee_id": str(s.employee_id),
        },
    )

    again = await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [{"amount": "1000", "method": "cash"}],
            "employee_id": str(s.employee_id),
        },
    )

    assert again.status_code == 409


async def test_a_negative_payment_is_rejected(client: AsyncClient) -> None:
    s = await _seed(client, ["32000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)

    resp = await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [{"amount": "-100", "method": "cash"}],
            "employee_id": str(s.employee_id),
        },
    )

    assert resp.status_code == 422


async def test_dissolving_returns_no_content_and_frees_the_orders(
    client: AsyncClient,
) -> None:
    s = await _seed(client, ["32000", "54000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)

    resp = await client.delete(f"/orders/table-bills/{bill['id']}", headers=headers)

    assert resp.status_code == 204
    # Y se puede volver a agrupar: las comandas quedaron libres.
    assert (await _open_bill(client, headers, s))["status"] == "open"


async def test_an_unknown_bill_is_a_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    resp = await client.get(f"/orders/table-bills/{uuid.uuid4()}", headers=headers)

    assert resp.status_code == 404


# --- Permisos -----------------------------------------------------------------
async def test_the_endpoints_are_permission_gated(client: AsyncClient) -> None:
    """Sin permiso nuevo: la misma autoridad que cobrar y cerrar una comanda."""
    bill_id = uuid.uuid4()

    for method, path in [
        ("post", "/orders/table-bills"),
        ("get", f"/orders/table-bills/{bill_id}"),
        ("delete", f"/orders/table-bills/{bill_id}"),
        ("post", f"/orders/table-bills/{bill_id}/payments"),
        ("post", f"/orders/table-bills/{bill_id}/receipts"),
    ]:
        # `get`/`delete` no aceptan cuerpo en httpx; el gate es lo que se prueba.
        resp = (
            await getattr(client, method)(path, json={})
            if method == "post"
            else await getattr(client, method)(path)
        )
        assert resp.status_code in (401, 403), f"{method} {path} → {resp.status_code}"


# --- Impresión ----------------------------------------------------------------
async def test_a_bill_receipt_is_first_then_reprint(client: AsyncClient) -> None:
    s = await _seed(client, ["32000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)
    body = {"employee_id": str(s.employee_id)}

    first = await client.post(
        f"/orders/table-bills/{bill['id']}/receipts", headers=headers, json=body
    )
    second = await client.post(
        f"/orders/table-bills/{bill['id']}/receipts", headers=headers, json=body
    )

    assert first.status_code == 201
    assert first.json()["is_reprint"] is False
    assert second.json()["is_reprint"] is True


async def test_a_bill_print_leaves_its_members_unprinted(client: AsyncClient) -> None:
    """Marcar las comandas convertiría una auditoría honesta en ruido."""
    s = await _seed(client, ["32000", "54000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)
    await client.post(
        f"/orders/table-bills/{bill['id']}/receipts",
        headers=headers,
        json={"employee_id": str(s.employee_id)},
    )

    # Imprimir DESPUÉS una comanda suelta sigue siendo su primera impresión.
    solo = await client.post(
        f"/orders/{s.order_ids[0]}/receipts",
        headers=headers,
        json={"employee_id": str(s.employee_id)},
    )

    assert solo.status_code == 201
    assert solo.json()["is_reprint"] is False


async def test_a_receipt_bound_to_neither_is_rejected(client: AsyncClient) -> None:
    """El caso de uso lo valida además del CHECK de la base."""
    from restaurante.modules.orders.application.use_cases.manage_orders import (
        OrderService,
    )
    from restaurante.modules.orders.infrastructure.repositories import (
        SqlAlchemyOrdersRepository,
    )
    from restaurante.shared.database import SessionFactory
    from restaurante.shared.domain.errors import ValidationError

    s = await _seed(client, ["32000"])
    async with SessionFactory() as session:
        service = OrderService(repo=SqlAlchemyOrdersRepository(session))
        for kwargs in ({}, {"order_id": s.order_ids[0], "table_bill_id": uuid.uuid4()}):
            try:
                await service.record_receipt_print(
                    s.tenant_id, s.employee_id, **kwargs
                )
            except ValidationError:
                continue
            raise AssertionError(f"tenía que rechazar {kwargs}")


async def test_the_receipt_carries_everything_the_paper_needs(
    client: AsyncClient,
) -> None:
    """La tirilla llega junta del servidor: un papel incompleto no se nota hasta entregarlo."""
    s = await _seed(client, ["32000", "54000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)
    await client.post(
        f"/orders/table-bills/{bill['id']}/payments",
        headers=headers,
        json={
            "payments": [
                {"amount": "40000", "method": "card"},
                {"amount": "46000", "method": "cash"},
            ],
            "employee_id": str(s.employee_id),
        },
    )

    body = (
        await client.get(f"/orders/table-bills/{bill['id']}/receipt", headers=headers)
    ).json()

    assert body["businessName"] if "businessName" in body else body["business_name"]
    assert body["total"] == "86000.00"
    # Los dos métodos con los que se pagó, para que el cliente reconozca su propio cobro.
    assert sorted(body["methods"]) == ["card", "cash"]
    assert len(body["members"]) == 2
    assert all(m["lines"] for m in body["members"])
    assert all(m["order_label"] for m in body["members"])
    # El servidor NO emite documento fiscal: no hay CUFE ni resolución aquí.
    assert body["is_fiscal_invoice"] is False


async def test_reading_the_receipt_does_not_record_a_print(client: AsyncClient) -> None:
    """Mirar la tirilla no es imprimirla: registrar la impresión es otro gesto."""
    s = await _seed(client, ["32000"])
    headers = await _login(client)
    bill = await _open_bill(client, headers, s)

    await client.get(f"/orders/table-bills/{bill['id']}/receipt", headers=headers)
    printed = await client.post(
        f"/orders/table-bills/{bill['id']}/receipts",
        headers=headers,
        json={"employee_id": str(s.employee_id)},
    )

    assert printed.json()["is_reprint"] is False
