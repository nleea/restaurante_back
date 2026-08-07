"""Orders/Salón realtime: order + table mutations publish; broker failure is non-fatal; SSE RBAC.

The publisher is swapped for an in-memory fake via the shared realtime deps' process-wide
publisher slot (monkeypatch restores it), so no Redis is needed — mirroring the KDS events test.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response

import restaurante.shared.realtime.deps as realtime_deps
from tests.modules._cash import seed_open_cash_session
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _login,
)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, uuid.UUID, dict[str, Any]]] = []

    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        self.events.append((topic, branch_id, payload))

    def kinds(self, topic: str) -> list[str]:
        return [p["kind"] for t, _b, p in self.events if t == topic]


class ExplodingPublisher:
    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        raise RuntimeError("broker down")


async def _open_takeaway_order(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID
) -> Response:
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    return await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "takeaway",
            "employee_id": str(employee_id),
        },
    )


async def test_opening_an_order_publishes_an_orders_event(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePublisher()
    monkeypatch.setattr(realtime_deps, "_event_publisher", fake)
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    resp = await _open_takeaway_order(client, headers, branch_id)
    assert resp.status_code == 201, resp.text
    assert "created" in fake.kinds("orders")


async def test_a_table_status_change_publishes_an_orders_event(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePublisher()
    monkeypatch.setattr(realtime_deps, "_event_publisher", fake)
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    created = await client.post(
        "/orders/tables",
        headers=headers,
        json={"branch_id": str(branch_id), "number": "7", "capacity": 4},
    )
    assert created.status_code == 201, created.text
    table_id = created.json()["id"]
    fake.events.clear()

    resp = await client.patch(
        f"/orders/tables/{table_id}", headers=headers, json={"capacity": 6}
    )
    assert resp.status_code == 200, resp.text
    assert "table" in fake.kinds("orders")


async def test_a_broker_failure_does_not_fail_the_mutation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(realtime_deps, "_event_publisher", ExplodingPublisher())
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    resp = await _open_takeaway_order(client, headers, branch_id)
    assert resp.status_code == 201, resp.text


async def test_events_stream_requires_permission(client: AsyncClient) -> None:
    # Authenticated but without any orders role: rejected before a byte is streamed.
    headers = await _login(client)
    resp = await client.get(
        "/orders/events", headers=headers, params={"branch_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 403
