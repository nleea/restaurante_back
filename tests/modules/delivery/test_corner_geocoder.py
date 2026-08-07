"""The chain, end to end with mocked transports: corner first, street pin as the fallback.

The case that drives every test here is the operator's report — `Calle 41A #12C - 48` pinned
onto Carrera 10, 555 m from the house, because the cross street was thrown away.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from restaurante.modules.delivery.infrastructure.corner_geocoder import CornerGeocoder
from restaurante.modules.delivery.infrastructure.geocoder import NominatimGeocoder
from restaurante.modules.delivery.infrastructure.overpass import OverpassCornerLookup
from restaurante.shared.cache.memory import InMemoryCache

# The branch's business pin — the bias, and the point the city is reverse-geocoded from.
BIAS_LAT = Decimal("11.5444")
BIAS_LON = Decimal("-72.9072")

# The corner the address actually sits on (measured against OSM geometry).
CORNER_LAT = Decimal("11.5228503")
CORNER_LON = Decimal("-72.9117535")

ADDRESS = "calle 41A #12C - 48, Riohacha"


class _Provider:
    """A fake pair of providers, recording what each was asked.

    `corners` holds the intersections OSM knows; anything else is a genuine miss.
    """

    def __init__(
        self,
        *,
        corners: dict[tuple[str, str], tuple[Decimal, Decimal]] | None = None,
        street_pin: tuple[Decimal, Decimal] | None = None,
        city: str | None = "Riohacha",
        overpass_status: int = 200,
    ) -> None:
        self.corners = corners or {}
        self.street_pin = street_pin
        self.city = city
        self.overpass_status = overpass_status
        self.asked_corners: list[tuple[str, str]] = []
        self.nominatim_searches: list[str] = []

    def overpass(self, request: httpx.Request) -> httpx.Response:
        if self.overpass_status != 200:
            return httpx.Response(self.overpass_status, text="gateway timeout")
        query = request.content.decode()
        pair = tuple(sorted(_names(query)))
        self.asked_corners.append(pair)  # type: ignore[arg-type]
        found = self.corners.get(pair) or self.corners.get(tuple(reversed(pair)))  # type: ignore[arg-type]
        if found is None:
            return httpx.Response(200, json={"elements": []})
        return httpx.Response(
            200,
            json={
                "elements": [
                    {"type": "node", "id": 1, "lat": str(found[0]), "lon": str(found[1])}
                ]
            },
        )

    def nominatim(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/reverse"):
            if self.city is None:
                return httpx.Response(200, json={"address": {}})
            return httpx.Response(200, json={"address": {"city": self.city}})
        asked = request.url.params.get("q", "")
        self.nominatim_searches.append(asked)
        if self.street_pin is None:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {
                    "lat": str(self.street_pin[0]),
                    "lon": str(self.street_pin[1]),
                    "display_name": asked,
                    # Verified against the street asked for, so echo it back.
                    "address": {"road": asked, "neighbourhood": "Centro"},
                }
            ],
        )


def _names(query: str) -> list[str]:
    """The two street names out of an Overpass QL body, in the order they were written."""
    import re
    from urllib.parse import parse_qs

    ql = parse_qs(query)["data"][0]
    return re.findall(r'way\(area\.a\)\["name"="([^"]+)"\]', ql)


def _geocoder(provider: _Provider) -> CornerGeocoder:
    cache = InMemoryCache()
    return CornerGeocoder(
        NominatimGeocoder(
            cache,
            base_url="https://nominatim.test",
            user_agent="tests/1.0",
            cache_ttl_seconds=60,
            transport=httpx.MockTransport(provider.nominatim),
        ),
        OverpassCornerLookup(
            cache,
            base_url="https://overpass.test",
            user_agent="tests/1.0",
            cache_ttl_seconds=60,
            transport=httpx.MockTransport(provider.overpass),
        ),
    )


class TestTheCornerWins:
    @pytest.mark.asyncio
    async def test_the_suffixed_street_misses_and_the_base_street_hits(self) -> None:
        """The address that started this: OSM has no Calle 41A, so 41 x 12C is the corner."""
        provider = _Provider(
            corners={("Calle 41", "Carrera 12C"): (CORNER_LAT, CORNER_LON)},
            street_pin=(Decimal("11.5237002"), Decimal("-72.9067338")),
        )
        result = await _geocoder(provider).geocode(
            ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is not None
        assert (result.latitude, result.longitude) == (CORNER_LAT, CORNER_LON)
        # The suffixed street was tried first, then traded down — in that order.
        assert provider.asked_corners == [
            ("Calle 41A", "Carrera 12C"),
            ("Calle 41", "Carrera 12C"),
        ]
        # A corner hit costs no search: the street pin is what we are replacing.
        assert provider.nominatim_searches == []

    @pytest.mark.asyncio
    async def test_the_exact_cross_is_exhausted_before_trading_down_to_its_base(
        self,
    ) -> None:
        """12C is the street the house is measured from; 12 is only the block beside it."""
        provider = _Provider(corners={("Calle 41", "Carrera 12"): (CORNER_LAT, CORNER_LON)})
        result = await _geocoder(provider).geocode(
            ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is not None
        assert provider.asked_corners == [
            ("Calle 41A", "Carrera 12C"),
            ("Calle 41", "Carrera 12C"),
            ("Calle 41A", "Carrera 12"),
            ("Calle 41", "Carrera 12"),
        ]

    @pytest.mark.asyncio
    async def test_the_first_corner_short_circuits_the_rest(self) -> None:
        provider = _Provider(corners={("Calle 41A", "Carrera 12C"): (CORNER_LAT, CORNER_LON)})
        await _geocoder(provider).geocode(ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON)
        assert provider.asked_corners == [("Calle 41A", "Carrera 12C")]


class TestTheFallback:
    @pytest.mark.asyncio
    async def test_no_corner_in_osm_falls_back_to_the_street_pin(self) -> None:
        """Worse, but not wrong — and strictly better than nothing."""
        pin = (Decimal("11.5237002"), Decimal("-72.9067338"))
        provider = _Provider(corners={}, street_pin=pin)
        result = await _geocoder(provider).geocode(
            ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is not None
        assert (result.latitude, result.longitude) == pin
        assert provider.nominatim_searches  # it really did fall through

    @pytest.mark.asyncio
    async def test_an_address_naming_no_cross_goes_straight_to_the_street_pin(
        self,
    ) -> None:
        pin = (Decimal("11.52"), Decimal("-72.90"))
        provider = _Provider(street_pin=pin)
        result = await _geocoder(provider).geocode(
            "Calle 20, Riohacha", bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is not None
        assert (result.latitude, result.longitude) == pin
        assert provider.asked_corners == []

    @pytest.mark.asyncio
    async def test_a_branch_with_no_business_pin_resolves_unbiased(self) -> None:
        """No bias means no city means no area to scope — but still an answer."""
        pin = (Decimal("11.52"), Decimal("-72.90"))
        provider = _Provider(street_pin=pin)
        result = await _geocoder(provider).geocode(ADDRESS)
        assert result is not None
        assert (result.latitude, result.longitude) == pin
        assert provider.asked_corners == []

    @pytest.mark.asyncio
    async def test_a_point_in_no_named_city_falls_back(self) -> None:
        pin = (Decimal("11.52"), Decimal("-72.90"))
        provider = _Provider(city=None, street_pin=pin)
        result = await _geocoder(provider).geocode(
            ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is not None
        assert (result.latitude, result.longitude) == pin
        assert provider.asked_corners == []

    @pytest.mark.asyncio
    async def test_nothing_anywhere_is_a_null_pin_not_an_error(self) -> None:
        provider = _Provider(corners={}, street_pin=None)
        assert (
            await _geocoder(provider).geocode(
                ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
            )
            is None
        )


class TestABrokenLookupDoesNotFallBack:
    @pytest.mark.asyncio
    async def test_overpass_down_yields_no_pin_rather_than_the_worse_one(self) -> None:
        """The rule that makes the sweeper work.

        Falling back here would write the 555 m-off street pin, which takes the row OUT of the
        "needs a pin" set — so one transient 504 would cost the corner permanently. No pin
        means the row is picked up again next pass.
        """
        provider = _Provider(
            overpass_status=504, street_pin=(Decimal("11.5237002"), Decimal("-72.9067338"))
        )
        result = await _geocoder(provider).geocode(
            ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
        )
        assert result is None
        assert provider.nominatim_searches == []

    @pytest.mark.asyncio
    async def test_a_geocode_never_raises_at_the_caller(self) -> None:
        """It is a side lookup: it must never break taking an order or abort a sweep."""
        provider = _Provider(overpass_status=504)
        assert (
            await _geocoder(provider).geocode(
                ADDRESS, bias_lat=BIAS_LAT, bias_lon=BIAS_LON
            )
            is None
        )
