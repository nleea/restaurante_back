"""Kitchen live-board events: publishing on route/advance, best-effort contract, SSE RBAC.

The publisher is swapped for an in-memory fake via the deps module's process-wide
publisher slot (monkeypatch restores it), so no Redis is needed.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

import restaurante.modules.kitchen.infrastructure.api.deps as kitchen_deps
from restaurante.modules.kitchen.domain.entities import KitchenEvent
from tests.modules.kitchen.test_kitchen_api import (
    _assign_role,
    _create_branch,
    _create_order_with_item,
    _create_product_and_variant,
    _create_station,
    _login,
)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[KitchenEvent] = []

    async def publish(self, event: KitchenEvent) -> None:
        self.events.append(event)


class ExplodingPublisher:
    async def publish(self, event: KitchenEvent) -> None:
        raise RuntimeError("broker down")


async def _routed_ticket(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[str, str]:
    """Station + product + order routed to one pending ticket. Returns (station_id, ticket_id)."""
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    product_id, variant_id = await _create_product_and_variant()
    await client.post(
        "/kitchen/product-stations",
        headers=headers,
        json={"product_id": str(product_id), "kitchen_station_id": str(station_id)},
    )
    order_id, _item_id = await _create_order_with_item(branch_id, variant_id)
    routed = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert routed.status_code == 201, routed.text
    return station_id, routed.json()[0]["id"]


async def test_route_and_advance_publish_events(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePublisher()
    monkeypatch.setattr(kitchen_deps, "_event_publisher", fake)
    await _assign_role("admin")
    headers = await _login(client)

    station_id, ticket_id = await _routed_ticket(client, headers)
    created = [e for e in fake.events if e.type == "ticket_created"]
    assert len(created) == 1
    assert str(created[0].station_id) == station_id
    assert created[0].status == "pending"
    assert created[0].order_id is not None

    resp = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert resp.status_code == 200
    advanced = [e for e in fake.events if e.type == "ticket_advanced"]
    assert len(advanced) == 1
    assert advanced[0].status == "in_progress"
    assert str(advanced[0].ticket_id) == ticket_id

    # Advancing to ready also resolves the order id for the rollup event.
    resp = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert resp.status_code == 200
    ready = [e for e in fake.events if e.status == "ready"]
    assert len(ready) == 1
    assert ready[0].order_id is not None


async def test_publish_failure_does_not_break_the_mutation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kitchen_deps, "_event_publisher", ExplodingPublisher())
    await _assign_role("admin")
    headers = await _login(client)

    station_id, ticket_id = await _routed_ticket(client, headers)
    resp = await client.post(f"/kitchen/tickets/{ticket_id}/advance", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    board = await client.get(
        f"/kitchen/stations/{station_id}/tickets", headers=headers
    )
    assert board.json()[0]["status"] == "in_progress"


async def test_events_stream_requires_permission(client: AsyncClient) -> None:
    # Authenticated but without any kitchen role: the stream must be rejected before
    # a single byte is streamed.
    headers = await _login(client)
    resp = await client.get(
        "/kitchen/events",
        headers=headers,
        params={"branch_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
