"""Delivery realtime: mutations + worker pin publish; broker failure non-fatal; SSE RBAC.

Service- and worker-level tests use a recording fake publisher (no Redis). The stream test only
checks the permission gate, mirroring the KDS events test.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from restaurante.modules.delivery.application.use_cases.geocode_pending import (
    PendingGeocoder,
)
from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from tests.modules.delivery.test_delivery_announce import (
    ORDER,
    TENANT,
)
from tests.modules.delivery.test_delivery_announce import (
    FakeRepo as AnnounceRepo,
)
from tests.modules.delivery.test_delivery_api import _login
from tests.modules.delivery.test_geocode_pending import (
    BRANCH_A,
    PIN_A,
    RESOLVED,
    FakeGeocoder,
    _delivery,
    _settings,
)
from tests.modules.delivery.test_geocode_pending import (
    FakeRepo as SweepRepo,
)


class RecordingPublisher:
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


class ExplodingPublisher:
    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        raise RuntimeError("broker down")


async def _no_sleep(_seconds: float) -> None:
    return None


async def test_create_delivery_publishes_a_delivery_event() -> None:
    pub = RecordingPublisher()
    service = DeliveryService(AnnounceRepo(), events=pub)  # type: ignore[arg-type]
    await service.create_delivery(TENANT, ORDER, "Calle 41A #12C-48")

    assert len(pub.events) == 1
    topic, _branch, payload = pub.events[0]
    assert topic == "delivery"
    assert payload["kind"] == "created"


async def test_a_broker_failure_does_not_fail_the_mutation() -> None:
    service = DeliveryService(AnnounceRepo(), events=ExplodingPublisher())  # type: ignore[arg-type]
    delivery = await service.create_delivery(TENANT, ORDER, "Calle 41A #12C-48")
    assert delivery.id is not None


async def test_worker_pin_resolution_publishes_a_delivery_event() -> None:
    """The cross-process case: a pin the worker resolves must notify the delivery's branch."""
    pub = RecordingPublisher()
    delivery = _delivery()
    repo = SweepRepo([delivery], settings={BRANCH_A: _settings(BRANCH_A, PIN_A)})
    sweeper = PendingGeocoder(
        repo,  # type: ignore[arg-type]
        FakeGeocoder([RESOLVED]),
        sleep=_no_sleep,
        events=pub,
    )
    await sweeper.run(10)

    assert len(pub.events) == 1
    topic, branch, payload = pub.events[0]
    assert (topic, branch) == ("delivery", delivery.branch_id)
    assert payload["kind"] == "pin"


async def test_events_stream_requires_permission(client: AsyncClient) -> None:
    # Authenticated but without any delivery role: rejected before a byte is streamed.
    headers = await _login(client)
    resp = await client.get(
        "/delivery/events", headers=headers, params={"branch_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 403
