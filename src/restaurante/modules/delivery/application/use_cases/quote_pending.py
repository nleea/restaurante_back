"""Bounded asynchronous delivery quote pass.

One pass does four things per delivery, in this order and no other:

1. measure the distance from the branch pin,
2. freeze the fee on the delivery AND the order total, atomically,
3. mint a single-use payment request,
4. hand the customer its link.

Step 4 lives here, in the same pass, and that is not an accident of layering. Only the token's
HASH reaches the database, so the readable link exists exactly once — inside step 3's return
value. A later worker reading `delivery_payment_requests` could not rebuild it. This is also why
a failed send is not retried: it is RE-ISSUED (see `reissue_payment_request`), because there is
nothing left to resend.

Steps 1–3 are money; step 4 is a consequence. A bridge that is down records a failed emission
and leaves the frozen quote exactly as it was.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from restaurante.modules.delivery.application.pricing import select_tariff_band
from restaurante.modules.delivery.domain.entities import (
    DeliveryPaymentRequest,
    DeliverySetting,
    DeliveryTariffBand,
    DistanceEstimate,
    OrderDelivery,
)
from restaurante.modules.delivery.domain.ports import (
    DeliveryRepository,
    DistanceEstimator,
)
from restaurante.modules.delivery.infrastructure.payment_requests import (
    issue_payment_token,
)
from restaurante.shared.config import get_settings
from restaurante.shared.customer_channel.ports import (
    EMISSION_NO_CONTACT,
    EMISSION_PENDING,
    DeliveryPaymentRequestNotifier,
)
from restaurante.shared.links import delivery_payment_url
from restaurante.shared.realtime.ports import EventPublisher

logger = logging.getLogger(__name__)

# A payment link outlives a normal working day but not a forgotten order. Long enough that a
# customer who pays "tonight" still can; short enough that a leaked link goes stale on its own.
PAYMENT_REQUEST_TTL_HOURS = 24

QUOTE_STATUS_QUOTED = "quoted"
QUOTE_STATUS_OUTSIDE_COVERAGE = "outside_coverage"
QUOTE_STATUS_UNQUOTABLE = "unquotable"

# Why a delivery could not be priced. Stored on the row so a dispatcher reads a sentence and not
# an absence — an unquotable delivery must never be indistinguishable from one still waiting.
REASON_NO_PLAN = "La sucursal no tiene bandas de tarifa configuradas."
REASON_NO_BRANCH_PIN = "La sucursal no tiene su ubicación configurada en el mapa."


class PendingQuoter:
    def __init__(
        self,
        repo: DeliveryRepository,
        estimator: DistanceEstimator,
        events: EventPublisher | None = None,
        notifier: DeliveryPaymentRequestNotifier | None = None,
    ) -> None:
        self._repo = repo
        self._estimator = estimator
        self._events = events
        self._notifier = notifier

    async def quote_one(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> bool:
        """Quote ONE delivery now, by id. Returns whether it got a price.

        This is the LATENCY path, and it exists because quoting is local arithmetic: unlike
        geocoding there is no provider, no rate limit and nothing to be polite to, so the only
        reason a quote ever waited was for coordinates to exist. The moment they do — an order
        taken with a GPS pin, or the geocode job landing one — there is nothing left to wait
        for, and making the customer wait up to a sweep tick for a Haversine was pure delay.

        `run()` remains the GUARANTEE: it reads the rows, so it still catches whatever this
        path drops.
        """
        delivery = await self._repo.get_delivery(tenant_id, delivery_id)
        if delivery is None or delivery.id is None:
            return False
        if delivery.quote_status not in ("pending_quote", QUOTE_STATUS_UNQUOTABLE):
            # Already quoted or outside coverage. Re-running would mint a second payment link
            # for a total the customer may already have been sent. `unquotable` IS retried:
            # what blocked it was the branch's configuration, not this delivery.
            return False
        if delivery.latitude is None or delivery.longitude is None:
            return False
        return await self._quote_one(delivery)

    async def run(self, limit: int) -> int:
        """Quote up to `limit` pending deliveries. Returns how many got a price.

        Deliberately NOT "how many rows were touched": a delivery marked outside coverage or
        unquotable was handled, but nobody was charged and nobody was messaged, and counting it
        as quoted would make a branch with no tariff plan look like a branch that is working.
        """
        quoted = 0
        for delivery in await self._repo.list_pending_quotes(limit):
            if delivery.id is None:
                continue
            if await self._quote_one(delivery):
                quoted += 1
        return quoted

    async def _quote_one(self, delivery: OrderDelivery) -> bool:
        assert delivery.id is not None  # guarded by the caller
        settings = await self._repo.get_settings_by_branch(delivery.tenant_id, delivery.branch_id)
        bands = await self._repo.list_tariff_bands(delivery.tenant_id, delivery.branch_id)
        reason = _unquotable_reason(settings, bands)
        if reason is not None:
            # Not a skip: a row that keeps saying `pending_quote` with no reason is a delivery
            # nobody can act on, retried silently on every pass, forever.
            await self._mark_unquotable(delivery, reason)
            return False
        assert settings is not None  # _unquotable_reason rejected the alternative
        origin_lat, origin_lon = settings.latitude, settings.longitude
        assert origin_lat is not None and origin_lon is not None

        destination_lat, destination_lon = delivery.latitude, delivery.longitude
        if destination_lat is None or destination_lon is None:
            # `list_pending_quotes` filters these out, so getting here means the row lost its
            # pin between the query and now. Re-pinning is the geocoder's job, not ours.
            return False

        estimate = await self._estimator.estimate(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
        )
        band = select_tariff_band(estimate.adjusted_km, bands)
        await self._repo.apply_quote(
            delivery.tenant_id,
            delivery.id,
            {
                "quote_status": (QUOTE_STATUS_QUOTED if band else QUOTE_STATUS_OUTSIDE_COVERAGE),
                "quote_raw_distance_km": estimate.raw_km,
                "quote_buffer_km": estimate.buffer_km,
                "quote_distance_km": estimate.adjusted_km,
                "quote_method": estimate.method,
                "quoted_fee": band.fee if band else None,
                "quoted_at": datetime.now(UTC),
                "quote_failure_reason": None,
            },
        )
        if band is None:
            # Out of coverage: no fee, no link, nothing to pay. The dispatcher decides whether
            # to call the customer or cancel — the system does not invent a price.
            logger.info(
                "Entrega %s fuera de cobertura (%.3f km ajustados)",
                delivery.id,
                estimate.adjusted_km,
            )
            await self._publish_quoted(delivery, estimate, fee=None)
            return False

        await self._issue_and_emit(delivery, estimate.adjusted_km, band.fee)
        await self._publish_quoted(delivery, estimate, fee=band.fee)
        return True

    async def _issue_and_emit(
        self, delivery: OrderDelivery, distance_km: Decimal, fee: Decimal
    ) -> None:
        """Mint the link and hand it over, then write down whether it arrived.

        A re-quote must not leave two live links quoting two different totals, so anything
        still pending for this delivery dies before the new one is born.
        """
        assert delivery.id is not None
        await self._repo.invalidate_payment_requests_for_delivery(delivery.tenant_id, delivery.id)
        raw_token, token_hash = issue_payment_token()
        request = await self._repo.create_payment_request(
            DeliveryPaymentRequest(
                tenant_id=delivery.tenant_id,
                branch_id=delivery.branch_id,
                order_id=delivery.order_id,
                order_delivery_id=delivery.id,
                token_hash=token_hash,
                quote_distance_km=distance_km,
                quoted_fee=fee,
                expires_at=datetime.now(UTC) + timedelta(hours=PAYMENT_REQUEST_TTL_HOURS),
                raw_token=raw_token,
            )
        )
        await self._emit(request, raw_token, fee)

    async def _emit(self, request: DeliveryPaymentRequest, raw_token: str, fee: Decimal) -> None:
        if request.id is None:  # pragma: no cover - the repository always assigns one
            return
        if self._notifier is None:
            await self._record_emission(
                request,
                EMISSION_PENDING,
                "La mensajería no está configurada en este proceso.",
            )
            return
        slug = await self._repo.tenant_slug(request.tenant_id)
        url = delivery_payment_url(get_settings().storefront_base_url, slug, raw_token)
        if not url:
            # Half a URL over WhatsApp is worse than none: the customer sees broken text and
            # concludes the system is broken. Say so on the row instead.
            await self._record_emission(
                request,
                EMISSION_NO_CONTACT,
                "Falta configurar la URL pública de la carta (STOREFRONT_BASE_URL).",
            )
            return
        outcome = await self._notifier.notify_delivery_payment_request(
            request.tenant_id,
            request.order_id,
            request_id=request.id,
            payment_url=url,
            delivery_fee=fee,
        )
        await self._record_emission(
            request,
            outcome.status,
            outcome.reason,
            emitted_at=datetime.now(UTC) if outcome.sent else None,
        )

    async def _record_emission(
        self,
        request: DeliveryPaymentRequest,
        status: str,
        reason: str | None,
        emitted_at: datetime | None = None,
    ) -> None:
        assert request.id is not None
        await self._repo.record_payment_request_emission(
            request.tenant_id,
            request.id,
            emission_status=status,
            reason=reason,
            emitted_at=emitted_at,
        )

    async def _mark_unquotable(self, delivery: OrderDelivery, reason: str) -> None:
        assert delivery.id is not None
        # Warning sólo la PRIMERA vez. La entrega se reintenta en cada barrido hasta que alguien
        # configure la sucursal, y un aviso por minuto por fila convertiría el log del worker en
        # ruido — que es como se deja de leer un log.
        if delivery.quote_status != QUOTE_STATUS_UNQUOTABLE:
            logger.warning(
                "Entrega %s no se puede cotizar (sucursal=%s): %s",
                delivery.id,
                delivery.branch_id,
                reason,
            )
        await self._repo.apply_quote(
            delivery.tenant_id,
            delivery.id,
            {
                "quote_status": QUOTE_STATUS_UNQUOTABLE,
                "quoted_fee": None,
                "quote_failure_reason": reason,
            },
        )

    async def _publish_quoted(
        self, delivery: OrderDelivery, estimate: DistanceEstimate, fee: Decimal | None
    ) -> None:
        """Nudge the dispatch board.

        Optional by construction, and checked: the worker can be built without a publisher
        (tests, a drain script), and calling into `None` here would abort a quote that has
        already been committed.
        """
        if self._events is None:
            return
        await self._events.publish(
            "QUOTED",
            delivery.tenant_id,
            delivery.branch_id,
            {
                "type": "delivery_quoted",
                "delivery_id": str(delivery.id),
                "order_id": str(delivery.order_id),
                "quoted_fee": str(fee) if fee is not None else None,
                "quote_distance_km": str(estimate.adjusted_km),
                "quote_method": estimate.method,
            },
        )


def _unquotable_reason(
    settings: DeliverySetting | None, bands: list[DeliveryTariffBand]
) -> str | None:
    """Why this delivery cannot be priced, or None when it can."""
    if settings is None or settings.latitude is None or settings.longitude is None:
        return REASON_NO_BRANCH_PIN
    if not bands:
        return REASON_NO_PLAN
    return None
