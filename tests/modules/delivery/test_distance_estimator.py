from decimal import Decimal

import pytest

from restaurante.modules.delivery.infrastructure.distance_estimator import (
    HaversineBufferedEstimator,
)


@pytest.mark.asyncio
async def test_haversine_estimator_adds_the_explicit_commercial_buffer() -> None:
    estimate = await HaversineBufferedEstimator().estimate(
        origin_lat=Decimal("6.2442"),
        origin_lon=Decimal("-75.5812"),
        destination_lat=Decimal("6.2442"),
        destination_lon=Decimal("-75.5812"),
    )

    assert estimate.raw_km == Decimal("0.000")
    assert estimate.buffer_km == Decimal("0.7")
    assert estimate.adjusted_km == Decimal("0.700")
    assert estimate.method == "haversine_buffered_v1"
