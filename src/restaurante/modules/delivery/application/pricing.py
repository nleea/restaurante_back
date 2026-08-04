"""Pure tariff selection used by the asynchronous delivery quote worker."""

from __future__ import annotations

from decimal import Decimal

from restaurante.modules.delivery.domain.entities import DeliveryTariffBand


def select_tariff_band(
    distance_km: Decimal, bands: list[DeliveryTariffBand]
) -> DeliveryTariffBand | None:
    """Return the first configured upper-bound that covers the adjusted distance."""
    for band in sorted(bands, key=lambda item: item.position):
        if distance_km <= band.max_distance_km:
            return band
    return None
