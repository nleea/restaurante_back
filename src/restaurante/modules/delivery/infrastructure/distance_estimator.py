"""Initial local distance estimator for delivery quotes.

It deliberately implements the same port a future road-routing gateway will use.  The buffer is
commercial policy, kept explicit in the returned estimate so quotes remain auditable.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import asin, cos, radians, sin, sqrt

from restaurante.modules.delivery.domain.entities import DistanceEstimate

_EARTH_RADIUS_KM = 6371.0088
_BUFFER_KM = Decimal("0.7")
_PRECISION = Decimal("0.001")


class HaversineBufferedEstimator:
    method = "haversine_buffered_v1"

    async def estimate(
        self,
        *,
        origin_lat: Decimal,
        origin_lon: Decimal,
        destination_lat: Decimal,
        destination_lon: Decimal,
    ) -> DistanceEstimate:
        lat1, lon1, lat2, lon2 = map(
            radians,
            (float(origin_lat), float(origin_lon), float(destination_lat), float(destination_lon)),
        )
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        raw = Decimal(str(_EARTH_RADIUS_KM * 2 * asin(sqrt(a)))).quantize(
            _PRECISION, rounding=ROUND_HALF_UP
        )
        return DistanceEstimate(
            raw_km=raw,
            buffer_km=_BUFFER_KM,
            adjusted_km=(raw + _BUFFER_KM).quantize(_PRECISION, rounding=ROUND_HALF_UP),
            method=self.method,
        )
