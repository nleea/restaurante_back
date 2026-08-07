"""The sweeper, with fakes — no network, no DB, no real second spent sleeping.

What a pass must get right: it picks only the rows that need a pin, it biases each one to its
OWN branch, and one bad delivery never costs the rest of the pass.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from restaurante.modules.delivery.application.use_cases.geocode_pending import (
    PendingGeocoder,
)
from restaurante.modules.delivery.domain.entities import (
    DeliverySetting,
    GeoResult,
    OrderDelivery,
)

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
BRANCH_A = uuid.uuid4()
BRANCH_B = uuid.uuid4()

PIN_A = (Decimal("11.5444"), Decimal("-72.9072"))
PIN_B = (Decimal("4.6097"), Decimal("-74.0817"))

RESOLVED = GeoResult(
    latitude=Decimal("11.5228503"),
    longitude=Decimal("-72.9117535"),
    neighborhood="Centro",
    display_name="Calle 41 x Carrera 12C, Riohacha",
)


def _delivery(
    *,
    tenant_id: uuid.UUID = TENANT_A,
    branch_id: uuid.UUID = BRANCH_A,
    address: str = "Calle 41A #12C-48",
    neighborhood: str | None = None,
) -> OrderDelivery:
    return OrderDelivery(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        branch_id=branch_id,
        order_id=uuid.uuid4(),
        address_text=address,
        neighborhood=neighborhood,
    )


class FakeRepo:
    """Only the three methods the sweeper touches."""

    def __init__(
        self,
        pending: list[OrderDelivery],
        *,
        settings: dict[uuid.UUID, DeliverySetting] | None = None,
    ) -> None:
        self._pending = pending
        self._settings = settings or {}
        self.asked_limit: int | None = None
        self.updates: list[tuple[uuid.UUID, uuid.UUID, dict[str, Any]]] = []

    async def list_pending_geocode(self, limit: int) -> list[OrderDelivery]:
        self.asked_limit = limit
        return self._pending[:limit]

    async def get_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting | None:
        return self._settings.get(branch_id)

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        self.updates.append((tenant_id, delivery_id, fields))
        return None


class FakeGeocoder:
    def __init__(self, results: list[GeoResult | None | Exception]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, Decimal | None, Decimal | None]] = []

    async def geocode(
        self,
        query: str,
        *,
        bias_lat: Decimal | None = None,
        bias_lon: Decimal | None = None,
    ) -> GeoResult | None:
        self.calls.append((query, bias_lat, bias_lon))
        outcome = self._results.pop(0) if self._results else None
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings(branch_id: uuid.UUID, pin: tuple[Decimal, Decimal]) -> DeliverySetting:
    return DeliverySetting(
        tenant_id=TENANT_A, branch_id=branch_id, latitude=pin[0], longitude=pin[1]
    )


async def _no_sleep(_seconds: float) -> None:
    return None


def _sweeper(repo: FakeRepo, geocoder: FakeGeocoder) -> PendingGeocoder:
    return PendingGeocoder(repo, geocoder, sleep=_no_sleep)  # type: ignore[arg-type]


class TestAPass:
    @pytest.mark.asyncio
    async def test_a_resolved_delivery_gets_its_pin_written_back(self) -> None:
        delivery = _delivery()
        repo = FakeRepo([delivery], settings={BRANCH_A: _settings(BRANCH_A, PIN_A)})
        report = await _sweeper(repo, FakeGeocoder([RESOLVED])).run(10)

        assert (report.found, report.resolved, report.unresolved) == (1, 1, 0)
        tenant_id, delivery_id, fields = repo.updates[0]
        assert (tenant_id, delivery_id) == (TENANT_A, delivery.id)
        assert fields["latitude"] == RESOLVED.latitude
        assert fields["longitude"] == RESOLVED.longitude

    @pytest.mark.asyncio
    async def test_nothing_pending_touches_nothing(self) -> None:
        """The second run of a pass that already did its work."""
        repo = FakeRepo([])
        geocoder = FakeGeocoder([])
        report = await _sweeper(repo, geocoder).run(10)

        assert (report.found, report.resolved) == (0, 0)
        assert geocoder.calls == []
        assert repo.updates == []

    @pytest.mark.asyncio
    async def test_the_pass_is_bounded(self) -> None:
        """A bounded pass is what keeps periodic runs from overlapping."""
        repo = FakeRepo([_delivery() for _ in range(5)])
        await _sweeper(repo, FakeGeocoder([])).run(3)
        assert repo.asked_limit == 3

    @pytest.mark.asyncio
    async def test_an_address_that_resolves_to_nothing_stays_pending(self) -> None:
        """No pin means the row stays in the set — that IS the retry."""
        repo = FakeRepo([_delivery()], settings={BRANCH_A: _settings(BRANCH_A, PIN_A)})
        report = await _sweeper(repo, FakeGeocoder([None])).run(10)

        assert (report.found, report.resolved, report.unresolved) == (1, 0, 1)
        assert repo.updates == []


class TestBias:
    @pytest.mark.asyncio
    async def test_each_delivery_is_biased_to_its_own_branch(self) -> None:
        """The sweeper crosses tenants, so the bias cannot come from anywhere but the row."""
        repo = FakeRepo(
            [
                _delivery(tenant_id=TENANT_A, branch_id=BRANCH_A),
                _delivery(tenant_id=TENANT_B, branch_id=BRANCH_B),
            ],
            settings={
                BRANCH_A: _settings(BRANCH_A, PIN_A),
                BRANCH_B: _settings(BRANCH_B, PIN_B),
            },
        )
        geocoder = FakeGeocoder([RESOLVED, RESOLVED])
        await _sweeper(repo, geocoder).run(10)

        assert [(lat, lon) for _, lat, lon in geocoder.calls] == [PIN_A, PIN_B]
        # And each pin is written back under its own tenant.
        assert [t for t, _, _ in repo.updates] == [TENANT_A, TENANT_B]

    @pytest.mark.asyncio
    async def test_a_branch_with_no_business_pin_resolves_unbiased_not_skipped(
        self,
    ) -> None:
        repo = FakeRepo([_delivery()], settings={})
        geocoder = FakeGeocoder([RESOLVED])
        report = await _sweeper(repo, geocoder).run(10)

        assert geocoder.calls[0][1:] == (None, None)
        assert report.resolved == 1


class TestNeighborhood:
    @pytest.mark.asyncio
    async def test_a_missing_neighborhood_is_filled_in(self) -> None:
        repo = FakeRepo([_delivery(neighborhood=None)])
        await _sweeper(repo, FakeGeocoder([RESOLVED])).run(10)
        assert repo.updates[0][2]["neighborhood"] == "Centro"

    @pytest.mark.asyncio
    async def test_a_neighborhood_the_operator_typed_is_never_overwritten(self) -> None:
        repo = FakeRepo([_delivery(neighborhood="San Martín")])
        await _sweeper(repo, FakeGeocoder([RESOLVED])).run(10)
        assert "neighborhood" not in repo.updates[0][2]

    @pytest.mark.asyncio
    async def test_a_corner_carries_no_barrio_and_that_is_not_an_error(self) -> None:
        """A corner hit skips Nominatim entirely, so there is no barrio to report."""
        corner = GeoResult(
            latitude=Decimal("11.5228503"),
            longitude=Decimal("-72.9117535"),
            neighborhood=None,
        )
        repo = FakeRepo([_delivery(neighborhood=None)])
        report = await _sweeper(repo, FakeGeocoder([corner])).run(10)

        assert report.resolved == 1
        assert "neighborhood" not in repo.updates[0][2]


class TestOneBadDeliveryDoesNotCostThePass:
    @pytest.mark.asyncio
    async def test_a_geocoder_that_raises_does_not_abort_the_pass(self) -> None:
        repo = FakeRepo([_delivery(), _delivery()])
        geocoder = FakeGeocoder([RuntimeError("provider exploded"), RESOLVED])
        report = await _sweeper(repo, geocoder).run(10)

        assert (report.found, report.resolved, report.unresolved) == (2, 1, 1)
        assert len(repo.updates) == 1

    @pytest.mark.asyncio
    async def test_a_write_that_fails_does_not_abort_the_pass(self) -> None:
        class ExplodingRepo(FakeRepo):
            async def update_delivery(
                self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
            ) -> OrderDelivery | None:
                if not self.updates:
                    self.updates.append((tenant_id, delivery_id, fields))
                    raise RuntimeError("deadlock")
                return await super().update_delivery(tenant_id, delivery_id, fields)

        repo = ExplodingRepo([_delivery(), _delivery()])
        report = await _sweeper(repo, FakeGeocoder([RESOLVED, RESOLVED])).run(10)

        assert (report.found, report.resolved) == (2, 1)


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_deliveries_are_paced_apart(self) -> None:
        """Both providers ask for ~1 req/s and neither is ours. The loop is the limiter."""
        paused: list[float] = []

        async def record(seconds: float) -> None:
            paused.append(seconds)

        repo = FakeRepo([_delivery() for _ in range(3)])
        sweeper = PendingGeocoder(
            repo,  # type: ignore[arg-type]
            FakeGeocoder([RESOLVED, RESOLVED, RESOLVED]),  # type: ignore[arg-type]
            sleep=record,
        )
        await sweeper.run(10)

        # Between the three, not before the first and not after the last.
        assert paused == [1.0, 1.0]
