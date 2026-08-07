from decimal import Decimal
from uuid import uuid4

from restaurante.modules.delivery.application.pricing import select_tariff_band
from restaurante.modules.delivery.domain.entities import DeliveryTariffBand


def _band(maximum: str, fee: str, position: int) -> DeliveryTariffBand:
    return DeliveryTariffBand(uuid4(), uuid4(), Decimal(maximum), Decimal(fee), position)


def test_selects_first_upper_bound_that_covers_adjusted_distance() -> None:
    selected = select_tariff_band(Decimal("2.700"), [_band("2", "3000", 0), _band("4", "5000", 1)])
    assert selected is not None
    assert selected.fee == Decimal("5000")


def test_returns_none_when_distance_is_outside_coverage() -> None:
    assert select_tariff_band(Decimal("4.001"), [_band("4", "5000", 0)]) is None
