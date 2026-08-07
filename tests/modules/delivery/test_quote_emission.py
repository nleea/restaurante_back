"""La cotización y la entrega del enlace de pago, que es lo que el cliente ve.

El invariante que sostiene el archivo: **la cotización es dinero y el mensaje es una
consecuencia**. Ninguna prueba de aquí puede terminar con una tarifa congelada distinta porque
WhatsApp se comportara distinto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from restaurante.modules.delivery.application.use_cases.quote_pending import (
    QUOTE_STATUS_OUTSIDE_COVERAGE,
    QUOTE_STATUS_QUOTED,
    QUOTE_STATUS_UNQUOTABLE,
    REASON_NO_BRANCH_PIN,
    REASON_NO_PLAN,
    PendingQuoter,
)
from restaurante.modules.delivery.domain.entities import (
    DeliveryPaymentRequest,
    DeliverySetting,
    DeliveryTariffBand,
    OrderDelivery,
)
from restaurante.modules.delivery.infrastructure.distance_estimator import (
    HaversineBufferedEstimator,
)
from restaurante.shared.customer_channel.ports import (
    EMISSION_FAILED,
    EMISSION_NO_CONTACT,
    EMISSION_PENDING,
    EMISSION_SENT,
    EmissionOutcome,
)

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()
ORDER = uuid.uuid4()
DELIVERY = uuid.uuid4()

# Riohacha: el pin del negocio y un punto a ~1 km. Coordenadas reales para que el colchón de
# 0,7 km se sume sobre una distancia que alguien puede comprobar en un mapa.
BRANCH_LAT, BRANCH_LON = Decimal("11.5444"), Decimal("-72.9072")
NEAR_LAT, NEAR_LON = Decimal("11.5534"), Decimal("-72.9072")


class FakeRepo:
    """Sólo lo que el cotizador toca. Registra escrituras para poder afirmar sobre ellas."""

    def __init__(
        self,
        *,
        deliveries: list[OrderDelivery] | None = None,
        settings: DeliverySetting | None = None,
        bands: list[DeliveryTariffBand] | None = None,
        slug: str | None = "demo",
    ) -> None:
        self._deliveries = deliveries or []
        self._settings = settings
        self._bands = bands or []
        self._slug = slug
        self.quotes: list[dict[str, Any]] = []
        self.created_requests: list[DeliveryPaymentRequest] = []
        self.emissions: list[dict[str, Any]] = []
        self.invalidated: list[uuid.UUID] = []

    async def list_pending_quotes(self, limit: int) -> list[OrderDelivery]:
        return self._deliveries[:limit]

    async def get_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting | None:
        return self._settings

    async def list_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryTariffBand]:
        return self._bands

    async def apply_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        self.quotes.append(fields)
        return None

    async def invalidate_payment_requests_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> int:
        self.invalidated.append(order_delivery_id)
        return 0

    async def create_payment_request(
        self, request: DeliveryPaymentRequest
    ) -> DeliveryPaymentRequest:
        request.id = uuid.uuid4()
        self.created_requests.append(request)
        return request

    async def record_payment_request_emission(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        emission_status: str,
        reason: str | None = None,
        emitted_at: datetime | None = None,
    ) -> None:
        self.emissions.append(
            {"status": emission_status, "reason": reason, "emitted_at": emitted_at}
        )

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None:
        return next((d for d in self._deliveries if d.id == delivery_id), None)

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        return self._slug


class RecordingNotifier:
    """Un canal que dice que sí y se queda con lo que le mandaron."""

    def __init__(self, outcome: EmissionOutcome | None = None) -> None:
        self.outcome = outcome or EmissionOutcome(sent=True, status=EMISSION_SENT)
        self.calls: list[dict[str, Any]] = []

    async def notify_delivery_payment_request(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        request_id: uuid.UUID,
        payment_url: str,
        delivery_fee: Decimal,
    ) -> EmissionOutcome:
        self.calls.append(
            {
                "order_id": order_id,
                "request_id": request_id,
                "payment_url": payment_url,
                "delivery_fee": delivery_fee,
            }
        )
        return self.outcome


class ExplodingNotifier:
    """Si el cotizador lo llama, la prueba falla. Para los caminos que no deben mensajear."""

    async def notify_delivery_payment_request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no debía emitirse ninguna solicitud de pago")


def _delivery(*, lat: Decimal = NEAR_LAT, lon: Decimal = NEAR_LON) -> OrderDelivery:
    return OrderDelivery(
        id=DELIVERY,
        tenant_id=TENANT,
        branch_id=BRANCH,
        order_id=ORDER,
        address_text="Calle 1 #2-3",
        latitude=lat,
        longitude=lon,
    )


def _settings(*, pinned: bool = True) -> DeliverySetting:
    return DeliverySetting(
        tenant_id=TENANT,
        branch_id=BRANCH,
        latitude=BRANCH_LAT if pinned else None,
        longitude=BRANCH_LON if pinned else None,
    )


def _bands(*maxima_and_fees: tuple[str, str]) -> list[DeliveryTariffBand]:
    return [
        DeliveryTariffBand(
            tenant_id=TENANT,
            branch_id=BRANCH,
            max_distance_km=Decimal(km),
            fee=Decimal(fee),
            position=index,
        )
        for index, (km, fee) in enumerate(maxima_and_fees)
    ]


def _quoter(repo: FakeRepo, notifier: Any = None) -> PendingQuoter:
    return PendingQuoter(repo, HaversineBufferedEstimator(), notifier=notifier)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _public_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin dominio público no hay enlace, y casi todo este archivo trata del enlace."""
    from restaurante.shared import config

    monkeypatch.setattr(
        config.get_settings(), "storefront_base_url", "https://wsquote.uk"
    )


class TestQuoteAndEmit:
    @pytest.mark.asyncio
    async def test_a_quoted_delivery_hands_the_customer_its_link(self) -> None:
        repo = FakeRepo(
            deliveries=[_delivery()],
            settings=_settings(),
            bands=_bands(("2", "3000"), ("4", "5000")),
        )
        notifier = RecordingNotifier()

        assert await _quoter(repo, notifier).run(10) == 1

        assert repo.quotes[0]["quote_status"] == QUOTE_STATUS_QUOTED
        assert len(notifier.calls) == 1
        call = notifier.calls[0]
        assert call["order_id"] == ORDER
        assert call["payment_url"].startswith(
            "https://demo.wsquote.uk/payment/delivery/"
        )
        assert call["delivery_fee"] == repo.quotes[0]["quoted_fee"]
        assert repo.emissions == [
            {
                "status": EMISSION_SENT,
                "reason": None,
                "emitted_at": repo.emissions[0]["emitted_at"],
            }
        ]
        assert repo.emissions[0]["emitted_at"] is not None

    @pytest.mark.asyncio
    async def test_the_link_carries_the_raw_token_and_the_row_only_its_hash(self) -> None:
        """El enlace sólo existe en esta pasada. Si la fila lo tuviera, sobraría reemitir."""
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )
        notifier = RecordingNotifier()

        await _quoter(repo, notifier).run(10)

        request = repo.created_requests[0]
        raw = notifier.calls[0]["payment_url"].rsplit("/", 1)[-1]
        assert raw and raw != request.token_hash
        from restaurante.modules.delivery.infrastructure.payment_requests import (
            hash_payment_token,
        )

        assert hash_payment_token(raw) == request.token_hash

    @pytest.mark.asyncio
    async def test_the_buffer_pushes_a_delivery_into_the_next_band(self) -> None:
        """~1 km reales + 0,7 de colchón = 1,7: paga la banda de 2 km, no la de 1."""
        repo = FakeRepo(
            deliveries=[_delivery()],
            settings=_settings(),
            bands=_bands(("1", "2000"), ("2", "4000")),
        )

        await _quoter(repo, RecordingNotifier()).run(10)

        assert repo.quotes[0]["quoted_fee"] == Decimal("4000")
        assert repo.quotes[0]["quote_buffer_km"] == Decimal("0.7")

    @pytest.mark.asyncio
    async def test_a_requote_kills_the_previous_link_before_minting_another(self) -> None:
        """Dos enlaces vivos son dos totales cobrables para el mismo pedido."""
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )

        await _quoter(repo, RecordingNotifier()).run(10)

        assert repo.invalidated == [DELIVERY]


class TestEmissionNeverCostsTheQuote:
    @pytest.mark.asyncio
    async def test_a_failed_send_leaves_the_frozen_fee_untouched(self) -> None:
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )
        notifier = RecordingNotifier(
            EmissionOutcome(sent=False, status=EMISSION_FAILED, reason="puente caído")
        )

        assert await _quoter(repo, notifier).run(10) == 1

        assert repo.quotes[0]["quote_status"] == QUOTE_STATUS_QUOTED
        assert repo.quotes[0]["quoted_fee"] == Decimal("5000")
        assert repo.emissions[0]["status"] == EMISSION_FAILED
        assert repo.emissions[0]["emitted_at"] is None

    @pytest.mark.asyncio
    async def test_an_order_without_whatsapp_is_recorded_not_failed(self) -> None:
        """Un pedido de mostrador no es un error: es un relevo a una persona."""
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )
        notifier = RecordingNotifier(
            EmissionOutcome(
                sent=False, status=EMISSION_NO_CONTACT, reason="sin contacto"
            )
        )

        await _quoter(repo, notifier).run(10)

        assert repo.emissions[0]["status"] == EMISSION_NO_CONTACT
        assert repo.created_requests, "la solicitud existe aunque nadie la reciba"

    @pytest.mark.asyncio
    async def test_without_a_public_domain_no_half_link_is_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Media URL por WhatsApp es peor que ninguna: el cliente cree que todo está roto."""
        from restaurante.shared import config

        monkeypatch.setattr(config.get_settings(), "storefront_base_url", "")
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )

        await _quoter(repo, ExplodingNotifier()).run(10)

        assert repo.emissions[0]["status"] == EMISSION_NO_CONTACT
        assert "STOREFRONT_BASE_URL" in (repo.emissions[0]["reason"] or "")

    @pytest.mark.asyncio
    async def test_without_a_configured_channel_the_quote_still_lands(self) -> None:
        """El worker arranca aunque el puente no esté montado."""
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )

        assert await _quoter(repo, None).run(10) == 1

        assert repo.quotes[0]["quoted_fee"] == Decimal("5000")
        assert repo.emissions[0]["status"] == EMISSION_PENDING

    @pytest.mark.asyncio
    async def test_no_publisher_does_not_abort_a_committed_quote(self) -> None:
        """`events` es opcional; llamarlo a ciegas tumbaba una cotización ya escrita."""
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )

        quoter = PendingQuoter(repo, HaversineBufferedEstimator(), events=None)  # type: ignore[arg-type]

        assert await quoter.run(10) == 1


class TestNothingIsPricedByGuessing:
    @pytest.mark.asyncio
    async def test_outside_coverage_charges_nothing_and_messages_nobody(self) -> None:
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("0.5", "2000"))
        )

        assert await _quoter(repo, ExplodingNotifier()).run(10) == 0

        assert repo.quotes[0]["quote_status"] == QUOTE_STATUS_OUTSIDE_COVERAGE
        assert repo.quotes[0]["quoted_fee"] is None
        assert repo.created_requests == []

    @pytest.mark.asyncio
    async def test_a_branch_without_bands_says_so_instead_of_waiting_forever(self) -> None:
        repo = FakeRepo(deliveries=[_delivery()], settings=_settings(), bands=[])

        assert await _quoter(repo, ExplodingNotifier()).run(10) == 0

        assert repo.quotes[0]["quote_status"] == QUOTE_STATUS_UNQUOTABLE
        assert repo.quotes[0]["quote_failure_reason"] == REASON_NO_PLAN
        assert repo.created_requests == []

    @pytest.mark.asyncio
    async def test_a_branch_without_a_pin_says_so(self) -> None:
        repo = FakeRepo(
            deliveries=[_delivery()],
            settings=_settings(pinned=False),
            bands=_bands(("4", "5000")),
        )

        assert await _quoter(repo, ExplodingNotifier()).run(10) == 0

        assert repo.quotes[0]["quote_failure_reason"] == REASON_NO_BRANCH_PIN

    @pytest.mark.asyncio
    async def test_an_unquotable_delivery_is_retried_once_the_branch_is_fixed(self) -> None:
        """Lo que la bloqueó fue la SUCURSAL, no ella. Dejarla fuera del barrido la vararía:
        sin precio para siempre, esperando un trabajo que nadie va a encolar."""
        stranded = _delivery()
        stranded.quote_status = QUOTE_STATUS_UNQUOTABLE
        repo = FakeRepo(
            deliveries=[stranded], settings=_settings(), bands=_bands(("4", "5000"))
        )

        assert await _quoter(repo, RecordingNotifier()).run(10) == 1

        assert repo.quotes[0]["quote_status"] == QUOTE_STATUS_QUOTED

    @pytest.mark.asyncio
    async def test_a_quoted_delivery_is_never_requoted_by_the_sweep(self) -> None:
        """Recotizarla acuñaría un segundo enlace por un total que el cliente ya recibió."""
        done = _delivery()
        done.quote_status = QUOTE_STATUS_QUOTED
        repo = FakeRepo(
            deliveries=[done], settings=_settings(), bands=_bands(("4", "5000"))
        )
        quoter = _quoter(repo, ExplodingNotifier())

        assert await quoter.quote_one(TENANT, DELIVERY) is False

    @pytest.mark.asyncio
    async def test_the_count_reports_priced_deliveries_not_touched_rows(self) -> None:
        """Contar los no cotizables haría que una sucursal mal configurada pareciera sana."""
        repo = FakeRepo(deliveries=[_delivery()], settings=_settings(), bands=[])

        assert await _quoter(repo, ExplodingNotifier()).run(10) == 0


class TestPaymentRequestShape:
    @pytest.mark.asyncio
    async def test_the_request_expires_and_freezes_the_quote_it_was_born_from(
        self,
    ) -> None:
        repo = FakeRepo(
            deliveries=[_delivery()], settings=_settings(), bands=_bands(("4", "5000"))
        )

        await _quoter(repo, RecordingNotifier()).run(10)

        request = repo.created_requests[0]
        assert request.quoted_fee == Decimal("5000")
        assert request.quote_distance_km == repo.quotes[0]["quote_distance_km"]
        assert request.expires_at > datetime.now(UTC)
        assert request.expires_at <= datetime.now(UTC) + timedelta(hours=24)
