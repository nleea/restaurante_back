"""The worker: resolving one announced delivery, and when to ask again.

No Redis, no worker process, no network. What matters here is what the job does NOT do: it
does not re-resolve a record that already has a pin (which is what makes a duplicate
announcement free), and it does not retry forever (the cron pass is the thing that never
gives up, not the job).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from restaurante.modules.delivery.application.use_cases.geocode_pending import (
    Outcome,
    PendingGeocoder,
)
from restaurante.modules.delivery.domain.entities import GeoResult, OrderDelivery
from restaurante.modules.delivery.infrastructure.worker import (
    MAX_TRIES,
    WorkerSettings,
    retry_after,
)

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()

PIN = (Decimal("11.5444"), Decimal("-72.9072"))

RESOLVED = GeoResult(
    latitude=Decimal("11.5228503"),
    longitude=Decimal("-72.9117535"),
    neighborhood="Centro",
)


def _delivery(
    *,
    address: str = "Calle 41A #12C-48",
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
) -> OrderDelivery:
    return OrderDelivery(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        branch_id=BRANCH,
        order_id=uuid.uuid4(),
        address_text=address,
        latitude=latitude,
        longitude=longitude,
    )


class FakeRepo:
    def __init__(self, delivery: OrderDelivery | None) -> None:
        self._delivery = delivery
        self.updates: list[tuple[uuid.UUID, uuid.UUID, dict[str, Any]]] = []

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None:
        return self._delivery

    async def get_settings_by_branch(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> None:
        return None

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        self.updates.append((tenant_id, delivery_id, fields))
        return None


class FakeGeocoder:
    def __init__(self, result: GeoResult | None) -> None:
        self._result = result
        self.calls = 0

    async def geocode(
        self,
        query: str,
        *,
        bias_lat: Decimal | None = None,
        bias_lon: Decimal | None = None,
    ) -> GeoResult | None:
        self.calls += 1
        return self._result


def _resolver(repo: FakeRepo, geocoder: FakeGeocoder) -> PendingGeocoder:
    return PendingGeocoder(repo, geocoder)  # type: ignore[arg-type]


class TestResolvingOneAnnouncedDelivery:
    @pytest.mark.asyncio
    async def test_a_pending_delivery_gets_its_pin_written(self) -> None:
        delivery = _delivery()
        repo, geocoder = FakeRepo(delivery), FakeGeocoder(RESOLVED)
        outcome = await _resolver(repo, geocoder).resolve_one(TENANT, delivery.id)  # type: ignore[arg-type]

        assert outcome is Outcome.RESOLVED
        _, _, fields = repo.updates[0]
        assert (fields["latitude"], fields["longitude"]) == (
            RESOLVED.latitude,
            RESOLVED.longitude,
        )

    @pytest.mark.asyncio
    async def test_an_already_located_delivery_is_untouched_and_costs_no_request(
        self,
    ) -> None:
        """Spec: "Resolving the same record twice changes nothing".

        This is what makes a duplicate announcement — or an announcement racing a pass —
        free: the record is re-read, and a pin that is already there ends it.
        """
        delivery = _delivery(latitude=PIN[0], longitude=PIN[1])
        repo, geocoder = FakeRepo(delivery), FakeGeocoder(RESOLVED)
        outcome = await _resolver(repo, geocoder).resolve_one(TENANT, delivery.id)  # type: ignore[arg-type]

        assert outcome is Outcome.NOT_NEEDED
        assert geocoder.calls == 0
        assert repo.updates == []

    @pytest.mark.asyncio
    async def test_a_hand_placed_pin_is_left_alone(self) -> None:
        """Spec: "A placed pin is left alone" — the operator outranks the provider."""
        delivery = _delivery(latitude=PIN[0], longitude=PIN[1])
        repo, geocoder = FakeRepo(delivery), FakeGeocoder(RESOLVED)

        outcome = await _resolver(repo, geocoder).resolve_one(TENANT, delivery.id)  # type: ignore[arg-type]

        assert outcome is Outcome.NOT_NEEDED
        assert repo.updates == []

    @pytest.mark.asyncio
    async def test_a_delivery_deleted_since_the_announcement_is_not_an_error(self) -> None:
        repo, geocoder = FakeRepo(None), FakeGeocoder(RESOLVED)
        outcome = await _resolver(repo, geocoder).resolve_one(TENANT, uuid.uuid4())

        assert outcome is Outcome.NOT_NEEDED
        assert geocoder.calls == 0

    @pytest.mark.asyncio
    async def test_no_pin_from_the_provider_is_unresolved_not_done(self) -> None:
        """The retryable outcome: the record still wants a pin."""
        delivery = _delivery()
        repo, geocoder = FakeRepo(delivery), FakeGeocoder(None)
        outcome = await _resolver(repo, geocoder).resolve_one(TENANT, delivery.id)  # type: ignore[arg-type]

        assert outcome is Outcome.UNRESOLVED
        assert repo.updates == []


class TestTheRetryIsBounded:
    def test_no_pin_is_retried_with_an_increasing_delay(self) -> None:
        assert [retry_after(Outcome.UNRESOLVED, t) for t in (1, 2, 3)] == [5, 10, 15]

    def test_it_stops_rather_than_retrying_forever(self) -> None:
        """The job lets go; the cron pass is what never gives up."""
        assert retry_after(Outcome.UNRESOLVED, MAX_TRIES) is None
        assert retry_after(Outcome.UNRESOLVED, MAX_TRIES + 1) is None

    def test_nothing_that_did_not_need_a_pin_is_ever_retried(self) -> None:
        assert retry_after(Outcome.RESOLVED, 1) is None
        assert retry_after(Outcome.NOT_NEEDED, 1) is None


class FakeResolver:
    """Stands in for `PendingGeocoder` inside the job, so no DB and no provider are needed."""

    def __init__(self, outcome: Outcome) -> None:
        self._outcome = outcome
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> FakeResolver:
        return self

    async def resolve_one(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> Outcome:
        self.calls += 1
        return self._outcome


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionFactory:
        return self

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> bool:
        return False


def _patch_job(monkeypatch: pytest.MonkeyPatch, outcome: Outcome) -> FakeResolver:
    from restaurante.modules.delivery.infrastructure import worker as worker_module

    resolver = FakeResolver(outcome)
    monkeypatch.setattr(worker_module, "SessionFactory", _FakeSessionFactory())
    monkeypatch.setattr(worker_module, "build_geocoder", lambda: FakeGeocoder(None))
    monkeypatch.setattr(worker_module, "SqlAlchemyDeliveryRepository", lambda s: None)
    monkeypatch.setattr(worker_module, "PendingGeocoder", resolver)
    return resolver


class TestTheJobItself:
    @pytest.mark.asyncio
    async def test_it_raises_retry_while_the_record_still_wants_a_pin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arq import Retry

        from restaurante.modules.delivery.infrastructure.worker import geocode_delivery

        _patch_job(monkeypatch, Outcome.UNRESOLVED)
        with pytest.raises(Retry) as raised:
            await geocode_delivery({"job_try": 2}, str(TENANT), str(uuid.uuid4()))

        assert raised.value.defer_score == 10_000  # arq stores the defer in ms

    @pytest.mark.asyncio
    async def test_it_lets_go_at_the_bound_instead_of_looping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The last try returns rather than raising: from here the cron pass owns it."""
        from restaurante.modules.delivery.infrastructure.worker import geocode_delivery

        _patch_job(monkeypatch, Outcome.UNRESOLVED)
        result = await geocode_delivery(
            {"job_try": MAX_TRIES}, str(TENANT), str(uuid.uuid4())
        )

        assert result == Outcome.UNRESOLVED.value

    @pytest.mark.asyncio
    async def test_a_resolved_delivery_ends_the_job(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from restaurante.modules.delivery.infrastructure.worker import geocode_delivery

        _patch_job(monkeypatch, Outcome.RESOLVED)
        result = await geocode_delivery({"job_try": 1}, str(TENANT), str(uuid.uuid4()))

        assert result == Outcome.RESOLVED.value


class TestTheRateLimitIsNotANegotiation:
    def test_the_worker_runs_one_job_at_a_time(self) -> None:
        """Nominatim and Overpass allow ~1 req/s and answer a breach with a silent ban.

        A test and not a comment because this is a requirement, and because the failure it
        prevents is invisible: raising this does not raise throughput, it stops pins for
        everyone and looks like the provider being slow.
        """
        assert WorkerSettings.max_jobs == 1

    def test_the_sweep_cannot_double_run(self) -> None:
        assert len(WorkerSettings.cron_jobs) == 2
        assert all(sweep.unique is True for sweep in WorkerSettings.cron_jobs)

    def test_every_announced_job_is_one_the_worker_runs(self) -> None:
        """A name drift here queues jobs forever and runs none of them."""
        from restaurante.modules.delivery.infrastructure.geocode_queue import (
            GEOCODE_DELIVERY_JOB,
            QUOTE_DELIVERY_JOB,
        )

        assert [f.name for f in WorkerSettings.functions] == [
            GEOCODE_DELIVERY_JOB,
            QUOTE_DELIVERY_JOB,
        ]
