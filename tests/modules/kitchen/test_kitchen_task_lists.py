"""Itemized station task lists: mapping config, PATCH in place, freeze-at-fire on tickets."""

from __future__ import annotations

from httpx import AsyncClient

from tests.modules.kitchen.test_kitchen_api import (
    _assign_role,
    _create_branch,
    _create_order_with_item,
    _create_product_and_variant,
    _create_station,
    _login,
)

TASKS = ["Carne de hamburguesa", "Tocineta ahumada"]


async def _mapped_product(
    client: AsyncClient, headers: dict[str, str], tasks: list[str] | None = None
) -> tuple[str, str, str, dict]:
    """Branch + station + product mapped (optionally with tasks). Returns ids + mapping."""
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, variant_id = await _create_product_and_variant()
    body: dict = {
        "product_id": str(product_id),
        "kitchen_station_id": str(station_id),
        "role": "Parrilla",
    }
    if tasks is not None:
        body["tasks"] = tasks
    resp = await client.post("/kitchen/product-stations", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return branch_id, station_id, variant_id, resp.json()


async def test_attach_with_tasks_and_default_empty(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    branch_id, _, _, mapping = await _mapped_product(client, headers, tasks=TASKS)
    assert mapping["tasks"] == TASKS

    # A second product without tasks defaults to an empty list.
    station_id = await _create_station(client, headers, branch_id, name="Fríos")
    product_id, _ = await _create_product_and_variant()
    resp = await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    assert resp.status_code == 201
    assert resp.json()["tasks"] == []


async def test_patch_updates_role_and_tasks_in_place(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    _, _, _, mapping = await _mapped_product(client, headers, tasks=["Carne"])

    patched = await client.patch(
        f"/kitchen/product-stations/{mapping['id']}",
        headers=headers,
        json={"tasks": ["  Carne de hamburguesa ", "Tocineta ahumada", "  "]},
    )
    assert patched.status_code == 200, patched.text
    # trimmed and empties dropped, same mapping id (no detach/re-attach)
    assert patched.json()["id"] == mapping["id"]
    assert patched.json()["tasks"] == TASKS
    assert patched.json()["role"] == "Parrilla"

    renamed = await client.patch(
        f"/kitchen/product-stations/{mapping['id']}",
        headers=headers,
        json={"role": "Plancha"},
    )
    assert renamed.json()["role"] == "Plancha"
    assert renamed.json()["tasks"] == TASKS  # untouched by a role-only patch


async def test_oversized_task_list_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    _, _, _, mapping = await _mapped_product(client, headers)

    too_many = await client.patch(
        f"/kitchen/product-stations/{mapping['id']}",
        headers=headers,
        json={"tasks": [f"Tarea {i}" for i in range(11)]},
    )
    assert too_many.status_code == 422

    too_long = await client.patch(
        f"/kitchen/product-stations/{mapping['id']}",
        headers=headers,
        json={"tasks": ["x" * 61]},
    )
    assert too_long.status_code == 422


async def test_routing_freezes_tasks_onto_tickets(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, station_id, variant_id, mapping = await _mapped_product(
        client, headers, tasks=TASKS
    )
    order_id, _ = await _create_order_with_item(branch_id, variant_id)

    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 201
    assert routed.json()[0]["tasks"] == TASKS

    # Editing the config never rewrites the fired ticket…
    await client.patch(
        f"/kitchen/product-stations/{mapping['id']}",
        headers=headers,
        json={"tasks": ["Solo carne"]},
    )
    board = await client.get(
        f"/kitchen/stations/{station_id}/tickets", headers=headers
    )
    assert board.json()[0]["tasks"] == TASKS

    # …but a subsequently routed order carries the new list.
    order2, _ = await _create_order_with_item(branch_id, variant_id)
    routed2 = await client.post(f"/kitchen/orders/{order2}/route", headers=headers)
    assert routed2.json()[0]["tasks"] == ["Solo carne"]


async def test_patch_requires_permission(client: AsyncClient) -> None:
    import uuid

    headers = await _login(client)  # authenticated, no kitchen role
    resp = await client.patch(
        f"/kitchen/product-stations/{uuid.uuid4()}",
        headers=headers,
        json={"tasks": []},
    )
    assert resp.status_code == 403
