"""The chain: the corner if OSM holds it, the street pin if it doesn't.

```
Overpass   Calle 41A x Carrera 12C   -> miss (41A is not in OSM)
Overpass   Calle 41  x Carrera 12C   -> HIT, the corner              <- the real address
Nominatim  Calle 41A / Calle 41      -> the street-level pin (the behaviour that predates this)
otherwise  no pin, placed by hand
```

The letter-suffix fallback that `address_co` already knew carries into the intersection: the
address that prompted all this, `Calle 41A #12C-48`, only resolves on the second line.

Nominatim is kept, not replaced. A street missing from OSM, or an address naming no cross,
still yields the street pin: worse, but not wrong, and strictly better than nothing.

One rule holds the whole thing together: **a broken lookup must not fall back**. Falling back
writes the worse pin, which takes the row out of the sweeper's "needs a pin" set — so a
transient Overpass 504 (1 request in 3 while probing) would permanently cost the corner. A
genuine no-match falls back; a failure returns nothing and is retried on the next pass.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from restaurante.modules.delivery.domain.entities import GeoResult
from restaurante.modules.delivery.infrastructure.address_co import StreetQuery, parse_street
from restaurante.modules.delivery.infrastructure.geo_errors import LookupFailed
from restaurante.modules.delivery.infrastructure.geocoder import NominatimGeocoder
from restaurante.modules.delivery.infrastructure.overpass import OverpassCornerLookup

_log = logging.getLogger(__name__)


class CornerGeocoder:
    """A `Geocoder` that resolves the address's corner, falling back to its street."""

    def __init__(self, nominatim: NominatimGeocoder, overpass: OverpassCornerLookup) -> None:
        self._nominatim = nominatim
        self._overpass = overpass

    async def geocode(
        self,
        query: str,
        *,
        bias_lat: Decimal | None = None,
        bias_lon: Decimal | None = None,
    ) -> GeoResult | None:
        try:
            corner = await self._corner(query, bias_lat, bias_lon)
        except LookupFailed as exc:
            # Not a fallback: see the module docstring. No pin, so the row stays in the
            # sweeper's set and the corner is tried again on the next pass.
            _log.warning("Corner lookup failed for %r: %s", query, exc)
            return None
        if corner is not None:
            return corner
        return await self._nominatim.geocode(query, bias_lat=bias_lat, bias_lon=bias_lon)

    async def _corner(
        self, query: str, bias_lat: Decimal | None, bias_lon: Decimal | None
    ) -> GeoResult | None:
        """The corner, or None when this address can't have one. Raises on a broken lookup."""
        if bias_lat is None or bias_lon is None:
            # No branch pin, so no city, so no area for Overpass to scope to. The street pin
            # is the best available answer — unbiased, but an answer.
            return None
        parsed = parse_street(query)
        if parsed is None or parsed.cross is None:
            # Junk, or an address naming only one street: there is no intersection to find.
            return None
        city = await self._nominatim.reverse_city(bias_lat, bias_lon)
        if city is None:
            return None

        for street, cross in _candidates(parsed):
            found = await self._overpass.corner(street, cross, city=city)
            if found is not None:
                lat, lon = found
                return GeoResult(
                    latitude=lat,
                    longitude=lon,
                    # A corner has no barrio to report: answering that would take another
                    # Nominatim request, and the whole point of a corner hit is not needing
                    # one. The caller keeps whatever neighborhood it was already given.
                    neighborhood=None,
                    display_name=f"{street} x {cross}, {city}",
                )
        return None


def _candidates(parsed: StreetQuery) -> list[tuple[str, str]]:
    """The corners to try, most specific first.

    The exact cross is exhausted against both streets before the base cross is tried: `12C` is
    the street the house is measured from, and `12` is only the block beside it. Trading down
    on the cross is a bigger concession than trading down on the street, so it happens later.
    """
    streets = [parsed.street]
    if parsed.base_street:
        streets.append(parsed.base_street)
    crosses = [parsed.cross]
    if parsed.base_cross:
        crosses.append(parsed.base_cross)
    return [(s, c) for c in crosses if c for s in streets]
