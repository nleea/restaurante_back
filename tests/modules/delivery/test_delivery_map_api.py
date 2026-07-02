"""Coverage-map slice: branch delivery settings, route map data, derived driver status."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.modules.delivery.test_delivery_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_route,
    _login,
)


# --- Branch delivery settings ---------------------------------------------------
async def test_settings_lazy_creation_and_update(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    # First read lazily creates the defaults: no pin, 1 km step.
    got = await client.get(f"/delivery/branches/{branch_id}/settings", headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["latitude"] is None
    assert body["longitude"] is None
    assert float(body["ring_step_km"]) == 1.0

    # Place the pin and widen the step.
    patched = await client.patch(
        f"/delivery/branches/{branch_id}/settings",
        headers=headers,
        json={"latitude": "6.2442000", "longitude": "-75.5812000", "ring_step_km": "1.5"},
    )
    assert patched.status_code == 200, patched.text
    assert float(patched.json()["latitude"]) == 6.2442
    assert float(patched.json()["ring_step_km"]) == 1.5

    again = await client.get(
        f"/delivery/branches/{branch_id}/settings", headers=headers
    )
    assert float(again.json()["longitude"]) == -75.5812


async def test_settings_step_out_of_range_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    too_wide = await client.patch(
        f"/delivery/branches/{branch_id}/settings",
        headers=headers,
        json={"ring_step_km": "9"},
    )
    assert too_wide.status_code == 422


async def test_settings_unknown_branch_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.get(
        f"/delivery/branches/{uuid.uuid4()}/settings", headers=headers
    )
    assert resp.status_code == 404


# --- Route map data ---------------------------------------------------------------
async def test_route_zones_color_and_position(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    first = await client.post(
        "/delivery/routes",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "name": "Ruta Centro",
            "zones": ["  Centro ", "La Candelaria", " "],
            "color": "#2563EB",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["zones"] == ["Centro", "La Candelaria"]  # trimmed, empties out
    assert first.json()["color"] == "#2563EB"
    assert first.json()["position"] == 0

    second = await client.post(
        "/delivery/routes",
        headers=headers,
        json={"branch_id": str(branch_id), "name": "Ruta Norte"},
    )
    assert second.json()["position"] == 1  # next band
    assert second.json()["zones"] == []
    assert second.json()["color"] is None

    # Update zones/color in place.
    patched = await client.patch(
        f"/delivery/routes/{second.json()['id']}",
        headers=headers,
        json={"zones": ["Chapinero"], "color": "#059669"},
    )
    assert patched.json()["zones"] == ["Chapinero"]
    assert patched.json()["color"] == "#059669"

    # Listing comes back in band order.
    listing = await client.get(
        "/delivery/routes", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert [r["position"] for r in listing.json()] == [0, 1]

    # Bad color and oversized zone list are rejected.
    bad_color = await client.patch(
        f"/delivery/routes/{second.json()['id']}",
        headers=headers,
        json={"color": "red"},
    )
    assert bad_color.status_code == 422
    too_many = await client.patch(
        f"/delivery/routes/{second.json()['id']}",
        headers=headers,
        json={"zones": [f"Zona {i}" for i in range(21)]},
    )
    assert too_many.status_code == 422


# --- Derived driver status ----------------------------------------------------------
async def test_driver_status_derivation(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    route_id = await _create_route(client, headers, branch_id)
    rider = await _create_employee(branch_id, "map-rider@demo.com")
    idle = await _create_employee(branch_id, "map-idle@demo.com")

    for employee_id in (rider, idle):
        attached = await client.post(
            f"/delivery/routes/{route_id}/drivers",
            headers=headers,
            json={"employee_id": str(employee_id)},
        )
        assert attached.status_code == 201, attached.text
        assert attached.json()["status"] == "available"

    # A run in `preparing` flips the rider to on_route; the other stays available.
    run = await client.post(
        "/delivery/runs",
        headers=headers,
        json={"delivery_route_id": str(route_id), "employee_id": str(rider)},
    )
    assert run.status_code == 201, run.text

    drivers = await client.get(
        f"/delivery/routes/{route_id}/drivers", headers=headers
    )
    by_employee = {d["employee_id"]: d["status"] for d in drivers.json()}
    assert by_employee[str(rider)] == "on_route"
    assert by_employee[str(idle)] == "available"

    # Finishing the run releases the rider.
    run_id = run.json()["id"]
    await client.post(f"/delivery/runs/{run_id}/depart", headers=headers)
    await client.post(f"/delivery/runs/{run_id}/finish", headers=headers)
    drivers2 = await client.get(
        f"/delivery/routes/{route_id}/drivers", headers=headers
    )
    by_employee2 = {d["employee_id"]: d["status"] for d in drivers2.json()}
    assert by_employee2[str(rider)] == "available"


async def test_settings_write_requires_manage(client: AsyncClient) -> None:
    headers = await _login(client)  # authenticated, no delivery role
    resp = await client.patch(
        f"/delivery/branches/{uuid.uuid4()}/settings",
        headers=headers,
        json={"ring_step_km": "2"},
    )
    assert resp.status_code == 403
