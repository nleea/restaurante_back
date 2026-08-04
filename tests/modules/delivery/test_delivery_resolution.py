"""Toda entrega puede llegar a un final.

Antes solo se podía resolver una entrega `in_transit`, así que un pedido cocinado que nunca
salió era inmortal. Con la caja bloqueándose por domicilios sin resolver, eso habría dejado
el turno trabado sin salida posible dentro del sistema.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.modules.delivery.test_delivery_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_order,
    _create_route,
    _login,
)


async def _pending_delivery(client: AsyncClient) -> tuple[dict[str, str], str, str]:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, f"res-{uuid.uuid4().hex[:6]}@demo.com")
    await client.post(
        f"/delivery/routes/{route_id}/drivers",
        headers=headers,
        json={"employee_id": str(driver)},
    )
    run_id = (
        await client.post(
            "/delivery/runs",
            headers=headers,
            json={"delivery_route_id": route_id, "employee_id": str(driver)},
        )
    ).json()["id"]
    order_id = await _create_order(branch_id, driver)
    delivery_id = (
        await client.post(
            "/delivery/deliveries",
            headers=headers,
            json={"order_id": str(order_id), "address_text": "Calle 9"},
        )
    ).json()["id"]
    return headers, run_id, delivery_id


async def _mark(
    client: AsyncClient, headers: dict[str, str], delivery_id: str, delivered: bool
):
    return await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": delivered, "reason": "Cliente canceló"},
    )


async def test_an_order_that_never_left_can_be_resolved(client: AsyncClient) -> None:
    headers, _run_id, delivery_id = await _pending_delivery(client)

    resp = await _mark(client, headers, delivery_id, delivered=False)

    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_status"] == "not_delivered"
    assert resp.json()["not_delivered_reason"] == "Cliente canceló"
    assert resp.json()["delivered_at"] is not None


async def test_an_assigned_delivery_can_be_resolved_before_departing(
    client: AsyncClient,
) -> None:
    headers, run_id, delivery_id = await _pending_delivery(client)
    assigned = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )
    assert assigned.status_code == 200

    resp = await _mark(client, headers, delivery_id, delivered=False)

    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_status"] == "not_delivered"


async def test_marking_delivered_before_departure_is_refused(
    client: AsyncClient,
) -> None:
    """No se puede entregar algo que sigue en el mostrador."""
    headers, _run_id, delivery_id = await _pending_delivery(client)

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )

    assert resp.status_code == 409, resp.text
    assert "en camino" in resp.json()["detail"]


async def test_a_resolved_delivery_cannot_be_resolved_again(
    client: AsyncClient,
) -> None:
    headers, _run_id, delivery_id = await _pending_delivery(client)
    first = await _mark(client, headers, delivery_id, delivered=False)
    assert first.status_code == 200

    second = await _mark(client, headers, delivery_id, delivered=False)

    assert second.status_code == 409, second.text
    assert "resuelta" in second.json()["detail"]


async def test_a_delivered_delivery_cannot_be_flipped_to_not_delivered(
    client: AsyncClient,
) -> None:
    headers, run_id, delivery_id = await _pending_delivery(client)
    await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )
    await client.post(f"/delivery/runs/{run_id}/depart", headers=headers)
    delivered = await client.post(
        f"/delivery/deliveries/{delivery_id}/mark-delivered",
        headers=headers,
        json={"delivered": True},
    )
    assert delivered.status_code == 200

    resp = await _mark(client, headers, delivery_id, delivered=False)

    assert resp.status_code == 409
