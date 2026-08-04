"""Live driver location: append-only trail, fat publish, dispatcher read, prune on finish.

Service-level tests use a tiny recording fake repo + fake publisher (no Redis, no DB). The
RBAC / only-active-runs / prune-through-the-API behaviours are driven end-to-end over the
delivery router, reusing the driver fixtures from `test_driver_run`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    POSITION_TOPIC,
    DeliveryService,
    _simplify_trail,
)
from restaurante.modules.delivery.domain.entities import (
    ActiveRunTrail,
    DeliveryRun,
    RunPosition,
)
from restaurante.modules.delivery.infrastructure.models import (
    DeliveryRunModel,
    DeliveryRunPositionModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.geo.simplify import simplify
from tests.modules.delivery.test_driver_run import (
    Ctx,
    _login,
    _make_driver,
    _pending_delivery,
)

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()
DRIVER = uuid.uuid4()
RUN = uuid.uuid4()


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


class FakeRepo:
    """Only the methods the position/finish paths touch."""

    def __init__(self, *, active_run: DeliveryRun | None) -> None:
        self._active_run = active_run
        self.appended: list[RunPosition] = []
        self.deleted: list[uuid.UUID] = []

    async def active_run_for_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun | None:
        return self._active_run

    async def append_position(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        branch_id: uuid.UUID,
        latitude: Decimal,
        longitude: Decimal,
    ) -> RunPosition:
        position = RunPosition(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            branch_id=branch_id,
            delivery_run_id=run_id,
            latitude=latitude,
            longitude=longitude,
            recorded_at=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        )
        self.appended.append(position)
        return position

    async def get_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> DeliveryRun | None:
        return self._active_run

    async def update_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRun | None:
        assert self._active_run is not None
        for key, value in fields.items():
            setattr(self._active_run, key, value)
        return self._active_run

    async def delete_run_positions(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        self.deleted.append(run_id)


def _run(status: str = "in_transit") -> DeliveryRun:
    return DeliveryRun(
        id=RUN,
        tenant_id=TENANT,
        branch_id=BRANCH,
        delivery_route_id=uuid.uuid4(),
        employee_id=DRIVER,
        status=status,
    )


# --- Douglas–Peucker --------------------------------------------------------
def test_douglas_peucker_reduces_straight_line_to_endpoints() -> None:
    line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 3.0), (0.0, 4.0)]
    assert simplify(line, 0.0001) == [(0.0, 0.0), (0.0, 4.0)]


def test_douglas_peucker_keeps_a_real_bend() -> None:
    # A sharp corner well above the tolerance survives.
    bent = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    assert simplify(bent, 0.0001) == bent


def test_simplify_trail_keeps_endpoints_and_recorded_at() -> None:
    base = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    trail = [
        RunPosition(
            tenant_id=TENANT,
            branch_id=BRANCH,
            delivery_run_id=RUN,
            latitude=Decimal("0.0"),
            longitude=Decimal(str(i)),
            recorded_at=base,
        )
        for i in range(5)
    ]
    kept = _simplify_trail(trail)
    assert [p.longitude for p in kept] == [Decimal("0"), Decimal("4")]


# --- record_my_position (service) -------------------------------------------
async def test_record_position_appends_and_publishes_fat_event() -> None:
    repo = FakeRepo(active_run=_run())
    pub = RecordingPublisher()
    service = DeliveryService(repo, events=pub)  # type: ignore[arg-type]

    position = await service.record_my_position(
        TENANT, DRIVER, Decimal("11.5448"), Decimal("-72.9072")
    )

    assert repo.appended == [position]
    assert len(pub.events) == 1
    topic, branch, payload = pub.events[0]
    assert (topic, branch) == (POSITION_TOPIC, BRANCH)
    assert payload["run_id"] == str(RUN)
    assert payload["employee_id"] == str(DRIVER)
    # JSON-safe: Decimals as strings, timestamp as ISO-8601.
    assert payload["latitude"] == "11.5448"
    assert payload["longitude"] == "-72.9072"
    assert payload["recorded_at"] == "2026-07-17T12:00:00+00:00"
    assert payload["branch_id"] == str(BRANCH)


async def test_record_position_without_active_run_is_rejected() -> None:
    repo = FakeRepo(active_run=None)
    service = DeliveryService(repo)  # type: ignore[arg-type]
    try:
        await service.record_my_position(TENANT, DRIVER, Decimal("1"), Decimal("2"))
    except ConflictError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ConflictError with no active run")
    assert repo.appended == []


async def test_broker_failure_does_not_fail_the_position_write() -> None:
    repo = FakeRepo(active_run=_run())
    service = DeliveryService(repo, events=ExplodingPublisher())  # type: ignore[arg-type]
    position = await service.record_my_position(
        TENANT, DRIVER, Decimal("1"), Decimal("2")
    )
    assert position.id is not None
    assert repo.appended == [position]


async def test_finish_run_prunes_the_trail() -> None:
    repo = FakeRepo(active_run=_run(status="in_transit"))
    service = DeliveryService(repo)  # type: ignore[arg-type]
    await service.finish_run(TENANT, RUN)
    assert repo.deleted == [RUN]


async def test_finish_run_publishes_removal_tombstone() -> None:
    repo = FakeRepo(active_run=_run(status="in_transit"))
    pub = RecordingPublisher()
    service = DeliveryService(repo, events=pub)  # type: ignore[arg-type]
    await service.finish_run(TENANT, RUN)

    # Exactly one driver_position frame — the tombstone that lets the dispatcher drop the
    # marker + trail at once, carrying no coordinates, flagged by event="finished".
    tombstones = [p for topic, _b, p in pub.events if topic == POSITION_TOPIC]
    assert tombstones == [
        {"event": "finished", "run_id": str(RUN), "branch_id": str(BRANCH)}
    ]


async def test_broker_failure_does_not_fail_finish_run() -> None:
    repo = FakeRepo(active_run=_run(status="in_transit"))
    service = DeliveryService(repo, events=ExplodingPublisher())  # type: ignore[arg-type]
    updated = await service.finish_run(TENANT, RUN)
    assert updated.status == "finished"
    assert repo.deleted == [RUN]


# --- API: RBAC + only-active-runs + prune -----------------------------------
async def _seed_position(
    ctx: Ctx, run_id: uuid.UUID, *, lat: str, lng: str
) -> None:
    async with SessionFactory() as session:
        session.add(
            DeliveryRunPositionModel(
                tenant_id=ctx.tenant_id,
                branch_id=ctx.branch_id,
                delivery_run_id=run_id,
                latitude=Decimal(lat),
                longitude=Decimal(lng),
            )
        )
        await session.commit()


async def _open_run(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/delivery/me/run", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["id"])


async def test_push_appends_to_own_active_run(client: AsyncClient) -> None:
    ctx = await _make_driver(routes=1)
    headers = await _login(client)
    await _pending_delivery(ctx.branch_id)
    run_id = await _open_run(client, headers)

    resp = await client.post(
        "/delivery/me/run/location",
        headers=headers,
        json={"latitude": "11.5448", "longitude": "-72.9072"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["run_id"] == str(run_id)
    assert body["latitude"] == "11.5448000"
    assert body["recorded_at"] is not None

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(DeliveryRunPositionModel).where(
                    DeliveryRunPositionModel.delivery_run_id == run_id
                )
            )
        ).scalars().all()
        assert len(rows) == 1


async def test_push_without_active_run_is_conflict(client: AsyncClient) -> None:
    await _make_driver(routes=1)
    headers = await _login(client)
    resp = await client.post(
        "/delivery/me/run/location",
        headers=headers,
        json={"latitude": "11.5", "longitude": "-72.9"},
    )
    assert resp.status_code == 409


async def test_push_without_drive_permission_is_forbidden(
    client: AsyncClient,
) -> None:
    await _make_driver(role="waiter", routes=0)  # no delivery.drive
    headers = await _login(client)
    resp = await client.post(
        "/delivery/me/run/location",
        headers=headers,
        json={"latitude": "11.5", "longitude": "-72.9"},
    )
    assert resp.status_code == 403


async def test_dispatcher_read_requires_read_permission(client: AsyncClient) -> None:
    await _make_driver(role="waiter", routes=0)  # no delivery.read
    headers = await _login(client)
    resp = await client.get(
        "/delivery/positions", headers=headers, params={"branch_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 403


async def test_positions_stream_requires_read_permission(client: AsyncClient) -> None:
    await _make_driver(role="waiter", routes=0)  # no delivery.read
    headers = await _login(client)
    resp = await client.get(
        "/delivery/positions/events",
        headers=headers,
        params={"branch_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403


async def test_dispatcher_read_returns_only_active_runs(client: AsyncClient) -> None:
    # The demo admin holds delivery.read; the courier fixture builds the branch + route.
    ctx = await _make_driver(role="courier", routes=1)
    headers = await _login(client)
    await _pending_delivery(ctx.branch_id)
    active_run = await _open_run(client, headers)

    # A finished run in the same branch with a stray position must not appear.
    async with SessionFactory() as session:
        finished = DeliveryRunModel(
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            delivery_route_id=ctx.route_ids[0],
            employee_id=ctx.employee_id,
            status="finished",
        )
        session.add(finished)
        await session.flush()
        finished_id = finished.id
        await session.commit()
    await _seed_position(ctx, active_run, lat="11.5", lng="-72.9")
    await _seed_position(ctx, finished_id, lat="10.0", lng="-70.0")

    resp = await client.get(
        "/delivery/positions", headers=headers, params={"branch_id": str(ctx.branch_id)}
    )
    assert resp.status_code == 200, resp.text
    runs = {r["run_id"] for r in resp.json()}
    assert runs == {str(active_run)}


async def test_finish_prunes_trail_through_the_api(client: AsyncClient) -> None:
    ctx = await _make_driver(role="courier", routes=1)
    headers = await _login(client)
    await _pending_delivery(ctx.branch_id)
    run_id = await _open_run(client, headers)
    await client.post(
        "/delivery/me/run/location",
        headers=headers,
        json={"latitude": "11.5", "longitude": "-72.9"},
    )
    await client.post(f"/delivery/me/runs/{run_id}/depart", headers=headers)
    finished = await client.post(f"/delivery/me/runs/{run_id}/finish", headers=headers)
    assert finished.status_code == 200

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(DeliveryRunPositionModel).where(
                    DeliveryRunPositionModel.delivery_run_id == run_id
                )
            )
        ).scalars().all()
        assert rows == []


def test_active_run_trail_entity_defaults() -> None:
    trail = ActiveRunTrail(run_id=RUN, employee_id=DRIVER)
    assert trail.trail == []
