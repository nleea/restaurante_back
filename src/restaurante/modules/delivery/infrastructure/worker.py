"""The process that gives deliveries their pins.

    poetry run arq restaurante.modules.delivery.infrastructure.worker.WorkerSettings

RUN EXACTLY ONE. Not one per host, not one per API replica — one. Nominatim and Overpass allow
roughly one request per second and answer a breach with a silent ban rather than an error, so a
second worker does not double throughput: it stops pins for everyone, quietly, and the symptom
looks like the provider being slow. `max_jobs = 1` holds the line inside this process; nothing
can hold it across two, which is why "how many workers" is a requirement in the spec and not a
knob in settings.

Two paths run here, and the difference is the whole design:

- `geocode_delivery` — a job, announced when an order is taken. This is the LATENCY: the pin
  lands in seconds instead of at the next tick. It may be lost, dropped, or never sent.
- `sweep_pending_geocodes` — a cron pass over `latitude IS NULL AND btrim(address_text) <> ''`.
  This is the GUARANTEE, and it is authoritative. It finds every pin-less record whether or not
  a job was ever enqueued for it: Redis down when the order was taken, a job that died, a code
  path that forgets to announce, or the rows already in the database.

Both run in this one worker, so a job cannot overlap a pass — they are serialised for free by
`max_jobs = 1`, and the ~1 req/s ceiling holds across both.

The worker runs with no tenant context and therefore sees every tenant's deliveries. That is
what a resolver needs; see `DeliveryRepository.list_pending_geocode`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq import Retry, cron, func
from arq.connections import RedisSettings

# Registers every model in Base.metadata (cross-module FKs).
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.delivery.application.use_cases.geocode_pending import (
    Outcome,
    PendingGeocoder,
)
from restaurante.modules.delivery.application.use_cases.quote_pending import PendingQuoter
from restaurante.modules.delivery.infrastructure.distance_estimator import (
    HaversineBufferedEstimator,
)
from restaurante.modules.delivery.infrastructure.geocode_queue import (
    GEOCODE_DELIVERY_JOB,
    QUOTE_DELIVERY_JOB,
)
from restaurante.modules.delivery.infrastructure.geocoder_factory import build_geocoder
from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.shared.config import get_settings
from restaurante.shared.database import SessionFactory
from restaurante.shared.realtime.deps import get_event_publisher

_log = logging.getLogger(__name__)

# Four tries at 5 s, 10 s, 15 s. Overpass sheds roughly one request in three and the address
# that motivated this took four attempts, so this resolves ~99% of corners within ~30 s — the
# immediacy the queue exists for. Past that the job lets go rather than retrying forever: the
# record still has an address and no pin, so the cron pass owns it from there.
MAX_TRIES = 4
_RETRY_STEP_SECONDS = 5


def retry_after(outcome: Outcome, job_try: int) -> int | None:
    """Seconds to defer before trying this delivery again, or None to let go.

    The whole retry policy, as a function of what happened and how many times we have asked.
    Only UNRESOLVED is retried: a record that is gone, already pinned, or hand-placed is
    NOT_NEEDED and asking again would never change that.

    Letting go is not giving up on the pin — it is handing the record back to the cron pass,
    which still has it, because the record and not the job is what says a pin is missing.
    """
    if outcome is Outcome.UNRESOLVED and job_try < MAX_TRIES:
        return job_try * _RETRY_STEP_SECONDS
    return None


async def geocode_delivery(ctx: dict[Any, Any], tenant_id: str, delivery_id: str) -> str:
    """Resolve one announced delivery. Returns the outcome, for the job log.

    Retrying on "no pin came back" deliberately does not tell a 504 apart from an address that
    matches nothing — the cache makes the distinction free. A transient failure is not cached,
    so the retry really re-asks; a genuine no-match IS cached, so the retry costs zero provider
    requests. Without a durable cache this would burn real requests on junk addresses, which is
    why CACHE_BACKEND=redis is a requirement and not a tuning note.
    """
    geocoder = build_geocoder()
    if geocoder is None:
        _log.error("Geocoding is disabled (geocoder_provider); dropping the job.")
        return Outcome.NOT_NEEDED.value

    # A session per job, closed with the block: this process is long-lived, and a session held
    # across jobs would pin a connection and serve stale reads to the next one.
    async with SessionFactory() as session:
        resolver = PendingGeocoder(
            SqlAlchemyDeliveryRepository(session),
            geocoder,
            events=get_event_publisher(),
        )
        outcome = await resolver.resolve_one(uuid.UUID(tenant_id), uuid.UUID(delivery_id))

    job_try: int = ctx.get("job_try", 1)
    defer = retry_after(outcome, job_try)
    if defer is not None:
        _log.info(
            "Geocode job: delivery %s unresolved on try %d; retrying in %ds.",
            delivery_id,
            job_try,
            defer,
        )
        raise Retry(defer=defer)

    if outcome is Outcome.UNRESOLVED:
        _log.info(
            "Geocode job: delivery %s unresolved after %d tries; leaving it to the sweep.",
            delivery_id,
            job_try,
        )
    else:
        _log.info("Geocode job: delivery %s %s.", delivery_id, outcome.value)

    if outcome is Outcome.RESOLVED:
        # The pin just landed, and quoting it is local arithmetic — no provider, no rate limit.
        # Doing it here rather than at the next sweep tick is what turns "your delivery costs
        # X" from a minute away into the same breath as the pin. The sweep still owns the
        # record if this throws.
        await _quote_now(uuid.UUID(tenant_id), uuid.UUID(delivery_id))
    return outcome.value


async def _quote_now(tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> bool:
    """Price one delivery immediately and hand the customer its link.

    Swallows on purpose: this is the accelerator. `sweep_pending_quotes` reads the rows and is
    what guarantees the price, so a failure here costs a tick — never a quote.
    """
    from restaurante.modules.messaging.infrastructure.api.deps import (
        build_customer_channel,
    )

    try:
        async with SessionFactory() as session:
            return await PendingQuoter(
                SqlAlchemyDeliveryRepository(session),
                HaversineBufferedEstimator(),
                events=get_event_publisher(),
                notifier=build_customer_channel(session),
            ).quote_one(tenant_id, delivery_id)
    except Exception:  # noqa: BLE001 - the sweep still owns the record
        _log.warning(
            "Immediate quote for delivery %s failed; the sweep will price it.",
            delivery_id,
            exc_info=True,
        )
        return False


async def quote_delivery(ctx: dict[Any, Any], tenant_id: str, delivery_id: str) -> str:
    """Price one announced, ALREADY-PINNED delivery. The GPS-order fast path.

    An order taken with coordinates never enters the geocoder, so nothing else would announce
    it and it would sit until the next sweep tick for a calculation that takes microseconds.
    """
    quoted = await _quote_now(uuid.UUID(tenant_id), uuid.UUID(delivery_id))
    return "quoted" if quoted else "not_needed"


async def sweep_pending_geocodes(ctx: dict[Any, Any]) -> str:
    """The periodic pass: the guarantee that no delivery is left without a pin.

    Reads the records, not the queue. Everything the queue can lose, this finds.
    """
    geocoder = build_geocoder()
    if geocoder is None:
        _log.error("Geocoding is disabled (geocoder_provider); nothing to sweep.")
        return "disabled"

    settings = get_settings()
    async with SessionFactory() as session:
        sweeper = PendingGeocoder(
            SqlAlchemyDeliveryRepository(session),
            geocoder,
            events=get_event_publisher(),
        )
        report = await sweeper.run(settings.geocode_sweep_limit)
    # The pass already logs found/resolved/pending. That line is this worker's only health
    # signal — nothing here supervises the process, and a worker that is silently dead looks
    # exactly like Overpass being slow.
    return f"{report.resolved}/{report.found}"


async def sweep_pending_quotes(ctx: dict[Any, Any]) -> str:
    """Quote pinned deliveries and hand each customer its payment link.

    The messaging channel is built here, on the same session, because the link is emitted
    inside the quoting pass — the raw token never reaches the database, so there is no later
    job that could send it. `build_customer_channel` is imported lazily for the same reason
    the API does it: this worker must still start when the bridge is not configured.
    """
    from restaurante.modules.messaging.infrastructure.api.deps import (
        build_customer_channel,
    )

    async with SessionFactory() as session:
        quoted = await PendingQuoter(
            SqlAlchemyDeliveryRepository(session),
            HaversineBufferedEstimator(),
            events=get_event_publisher(),
            notifier=build_customer_channel(session),
        ).run(get_settings().geocode_sweep_limit)
    return str(quoted)


class WorkerSettings:
    """The arq worker. `arq <this class's dotted path>`."""

    # Named from the constant the announcer enqueues, so the two sides cannot drift apart
    # into a job that is queued forever and never run.
    functions = [
        func(geocode_delivery, name=GEOCODE_DELIVERY_JOB),
        func(quote_delivery, name=QUOTE_DELIVERY_JOB),
    ]
    cron_jobs = [
        cron(
            sweep_pending_geocodes,
            # Every `geocode_sweep_minute_step` minutes, at second 0.
            minute=set(range(0, 60, get_settings().geocode_sweep_minute_step)),
            second=0,
            # arq's default, stated because it is load-bearing: were a second worker ever
            # started, the sweep would still not double-run. A partial guard only — two
            # workers would still take two queued jobs at once. Exactly one worker.
            unique=True,
        ),
        cron(
            sweep_pending_quotes,
            minute=set(range(0, 30, get_settings().geocode_sweep_minute_step)),
            second=30,
            unique=True,
        ),
    ]

    # NOT a tuning knob. The providers' ~1 req/s is a ceiling on the whole system, so the
    # resolver is not horizontally scalable and its concurrency is pinned here at one. Raising
    # this is a silent ban, not a speedup. Asserted by a test, for that reason.
    max_jobs = 1

    # arq's default keep_result is 3600s; the outcome string is small and a job's history is
    # the only trace of what a lost pin did.
    max_tries = MAX_TRIES

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

    @staticmethod
    async def on_startup(ctx: dict[Any, Any]) -> None:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        _log.info(
            "Delivery geocoding worker up: max_jobs=%d, sweeping %d records every %d min.",
            WorkerSettings.max_jobs,
            get_settings().geocode_sweep_limit,
            get_settings().geocode_sweep_minute_step,
        )
