"""No se despacha lo que la cocina no ha terminado.

El bug que esto cierra: el registro de entrega nace al abrir el pedido (para capturar la
dirección y geocodificar el pin), así que Despacho lo veía desde el minuto cero y podía
asignarlo y marcarlo entregado sin que la cocina hubiera visto nada.
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


async def _setup(
    client: AsyncClient, kitchen_state: str
) -> tuple[dict[str, str], str, str, uuid.UUID]:
    """Un despacho en preparación y una entrega cuyo pedido está en `kitchen_state`."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    driver = await _create_employee(branch_id, f"gate-{uuid.uuid4().hex[:6]}@demo.com")
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
    order_id = await _create_order(branch_id, driver, kitchen_state=kitchen_state)
    delivery_id = (
        await client.post(
            "/delivery/deliveries",
            headers=headers,
            json={"order_id": str(order_id), "address_text": "Calle 9"},
        )
    ).json()["id"]
    return headers, run_id, delivery_id, branch_id


async def test_assigning_a_cooked_order_succeeds(client: AsyncClient) -> None:
    headers, run_id, delivery_id, _branch = await _setup(client, "ready")

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_status"] == "assigned"


async def test_assigning_an_order_still_in_the_kitchen_is_refused(
    client: AsyncClient,
) -> None:
    headers, run_id, delivery_id, branch_id = await _setup(client, "in_kitchen")

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )

    assert resp.status_code == 409, resp.text
    assert "cocina" in resp.json()["detail"].lower()

    # La entrega no se movió: sigue disponible para cuando la cocina termine.
    listed = await client.get(
        "/delivery/deliveries", headers=headers, params={"branch_id": str(branch_id)}
    )
    row = next(d for d in listed.json() if d["id"] == delivery_id)
    assert row["delivery_status"] == "pending"
    assert row["delivery_run_id"] is None


async def test_assigning_an_order_that_never_reached_the_kitchen_is_refused(
    client: AsyncClient,
) -> None:
    # `none` = el pedido no tiene ni un ticket de cocina. Es el caso que se vio en producción:
    # entregado sin haber pasado nunca por la cocina.
    headers, run_id, delivery_id, _branch = await _setup(client, "none")

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )

    assert resp.status_code == 409, resp.text


async def test_the_gate_does_not_care_about_the_payment_method(
    client: AsyncClient,
) -> None:
    """El método de pago decide cuándo entra la plata, nunca cuándo sale la comida."""
    headers, run_id, delivery_id, _branch = await _setup(client, "in_kitchen")

    resp = await client.post(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=headers,
        json={"delivery_run_id": run_id},
    )

    assert resp.status_code == 409


async def test_listing_reports_kitchen_state_so_dispatch_can_block(
    client: AsyncClient,
) -> None:
    headers, _run_id, delivery_id, branch_id = await _setup(client, "in_kitchen")

    listed = await client.get(
        "/delivery/deliveries",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )
    assert listed.status_code == 200, listed.text
    row = next(d for d in listed.json() if d["id"] == delivery_id)
    # Despacho necesita el motivo para pintar el bloqueo, en vez de dejar que el asignar
    # falle contra el servidor.
    assert row["kitchen_state"] == "in_kitchen"
