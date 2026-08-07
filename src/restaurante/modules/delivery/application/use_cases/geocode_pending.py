"""The sweeper: give a pin to the deliveries that don't have one.

Taking an order no longer waits on a geocoder — it stores the address and returns. This is
what closes the loop afterwards, and the queue it reads is a predicate, not a broker:

    latitude IS NULL AND btrim(address_text) <> ''

Idempotent (a resolved pin leaves the set), restart-safe (the state is the row), self-retrying
(a failure simply stays in the set), and it picks up the deliveries already stored without a
pin without being told about them.

It runs **without tenant context**, so it sees every tenant's rows — see
`DeliveryRepository.list_pending_geocode`. Safe only because it answers no one: it reads rows,
resolves pins, writes them back. Each delivery is biased to *its own* branch.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from restaurante.modules.delivery.domain.entities import OrderDelivery
from restaurante.modules.delivery.domain.ports import DeliveryRepository, Geocoder
from restaurante.shared.realtime.ports import EventPublisher

# Same topic the DeliveryService publishes on: a pin resolved in the worker process must reach
# the very same branch streams a dispatcher's mutation does. Kept in sync with
# `manage_delivery.EVENT_TOPIC`.
EVENT_TOPIC = "delivery"

_log = logging.getLogger(__name__)

# One delivery at a time with a pause between them: the loop is the rate limiter. Both
# providers ask for ~1 req/s and neither is ours. Nothing tunes this because nothing should.
_PAUSE_SECONDS = 1.0


class Outcome(Enum):
    """What resolving one announced delivery did — the worker's retry decision.

    The distinction that matters is NOT_NEEDED vs. UNRESOLVED: the first is a record that
    never wanted a pin from us (gone, hand-placed, already swept), the second is one that
    still does. Only the second is worth another try.
    """

    RESOLVED = "resolved"
    NOT_NEEDED = "not_needed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SweepReport:
    """What a pass did — the whole observable surface of a scheduled job."""

    found: int
    resolved: int

    @property
    def unresolved(self) -> int:
        """Still pin-less: no match, or a provider that couldn't be asked. Retried next pass."""
        return self.found - self.resolved


class PendingGeocoder:
    def __init__(
        self,
        repo: DeliveryRepository,
        geocoder: Geocoder,
        *,
        pause_seconds: float = _PAUSE_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        events: EventPublisher | None = None,
    ) -> None:
        self._repo = repo
        self._geocoder = geocoder
        self._pause_seconds = pause_seconds
        # Injectable so tests don't spend a real second per delivery.
        self._sleep = sleep
        # Best-effort live-board publisher. THIS is the cross-process case that mandates Redis:
        # the worker is a separate process, so an in-process bus would silently miss the pin it
        # just resolved. Absent → no notification (the map still refreshes on its poll).
        self._events = events

    async def run(self, limit: int) -> SweepReport:
        """Resolve up to `limit` pin-less deliveries, then return. Bounded on purpose.

        A bounded pass keeps periodic runs from overlapping, and a script cannot accidentally
        multiply with the web tier the way an in-app loop would under `--workers 4`.
        """
        pending = await self._repo.list_pending_geocode(limit)
        if not pending:
            _log.info("Geocoding sweep: nothing pending.")
            return SweepReport(found=0, resolved=0)

        resolved = 0
        for index, delivery in enumerate(pending):
            if index:
                await self._sleep(self._pause_seconds)
            if await self._resolve(delivery):
                resolved += 1

        report = SweepReport(found=len(pending), resolved=resolved)
        _log.info(
            "Geocoding sweep: %d found, %d resolved, %d still pending.",
            report.found,
            report.resolved,
            report.unresolved,
        )
        return report

    async def resolve_one(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> Outcome:
        """Pin ONE delivery that was announced as needing it. Same resolution as a pass.

        The record is re-read rather than trusted from the announcement, and that re-read is
        what makes a duplicate announcement free: by the time this runs a pass may already
        have pinned the row, the operator may have placed the pin by hand, or the record may
        be gone. All three are NOT_NEEDED — nothing to do, and no provider request spent.

        Never raises: the caller is a job, and a job that raises here would retry an error
        this can already describe.
        """
        delivery = await self._repo.get_delivery(tenant_id, delivery_id)
        if delivery is None:
            # Announced and then deleted. Not our problem, and not a failure.
            return Outcome.NOT_NEEDED
        if delivery.latitude is not None or delivery.longitude is not None:
            # Already carries a location, derived or hand-placed. Never re-resolved.
            return Outcome.NOT_NEEDED
        if not delivery.address_text.strip():
            # Not in the predicate's set: an address of spaces is not an address.
            return Outcome.NOT_NEEDED
        return Outcome.RESOLVED if await self._resolve(delivery) else Outcome.UNRESOLVED

    async def _resolve(self, delivery: OrderDelivery) -> bool:
        """Pin one delivery. Never raises: one bad address must not abort the pass."""
        if delivery.id is None:  # pragma: no cover - it was just read from the database
            return False
        try:
            bias_lat, bias_lon = await self._bias(delivery)
            result = await self._geocoder.geocode(
                delivery.address_text, bias_lat=bias_lat, bias_lon=bias_lon
            )
            if result is None:
                # Either the address matches nothing or a provider was down. Both leave the
                # row in the set, which is the retry.
                return False
            fields: dict[str, object] = {
                "latitude": result.latitude,
                "longitude": result.longitude,
            }
            # A corner hit carries no barrio; never blank one that is already there.
            if not delivery.neighborhood and result.neighborhood:
                fields["neighborhood"] = result.neighborhood
            await self._repo.update_delivery(delivery.tenant_id, delivery.id, fields)
        except Exception:  # noqa: BLE001 - one delivery's problem is not the pass's problem
            _log.exception("Geocoding sweep: delivery %s failed", delivery.id)
            return False
        # The pin is written: tell the delivery's branch so the coverage map lights up now
        # instead of at the next poll. Best-effort — a publish failure never un-resolves a pin.
        await self._publish_pin(delivery)
        return True

    async def _publish_pin(self, delivery: OrderDelivery) -> None:
        if self._events is None:
            return
        try:
            await self._events.publish(
                EVENT_TOPIC,
                delivery.tenant_id,
                delivery.branch_id,
                {"kind": "pin", "branch_id": str(delivery.branch_id)},
            )
        except Exception:  # noqa: BLE001 - notification is a non-blocking side effect
            _log.warning(
                "Geocoding: publishing pin for delivery %s failed",
                delivery.id,
                exc_info=True,
            )

    async def _bias(self, delivery: OrderDelivery) -> tuple[Decimal | None, Decimal | None]:
        """This delivery's own branch pin — the bias, and the city the corner is scoped to.

        A branch that never placed its pin resolves unbiased rather than being skipped: a
        street-level pin somewhere in Colombia still beats no pin at all.
        """
        settings = await self._repo.get_settings_by_branch(delivery.tenant_id, delivery.branch_id)
        if settings is None:
            return None, None
        return settings.latitude, settings.longitude
