"""Unit tests for NominatimGeocoder — mocked httpx transport, no network.

Verify the request it builds (query, country filter, viewbox bias, User-Agent), how it
parses the top hit, that misses return None, and that results are cached (a second call
does not hit the transport).
"""

from __future__ import annotations

from decimal import Decimal

import httpx

from restaurante.modules.delivery.infrastructure.geocoder import NominatimGeocoder
from restaurante.shared.cache.memory import InMemoryCache

HIT = [
    {
        "lat": "11.5369275",
        "lon": "-72.9106736",
        "display_name": "Calle 20, Riohacha, La Guajira, Colombia",
        # `road` carries the street the match actually stands on — the adapter checks it
        # against the street it asked for, so a match without one cannot be verified.
        "address": {
            "road": "Calle 20",
            "neighbourhood": "Nuestra Señora de los Remedios",
        },
    }
]


def _geocoder(handler) -> NominatimGeocoder:
    return NominatimGeocoder(
        InMemoryCache(),
        base_url="https://nominatim.test",
        user_agent="restaurante-app/1.0 (contacto: test)",
        cache_ttl_seconds=3600,
        transport=httpx.MockTransport(handler),
    )


async def test_builds_biased_request_and_parses_hit() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=HIT)

    geo = _geocoder(handler)
    result = await geo.geocode(
        "Calle 20", bias_lat=Decimal("11.54"), bias_lon=Decimal("-72.91")
    )

    assert result is not None
    assert result.latitude == Decimal("11.5369275")
    assert result.longitude == Decimal("-72.9106736")
    assert result.neighborhood == "Nuestra Señora de los Remedios"

    req = seen[0]
    assert req.url.path == "/search"
    params = dict(req.url.params)
    assert params["countrycodes"] == "co"
    assert params["q"] == "Calle 20"
    assert params["bounded"] == "1"
    assert "viewbox" in params  # biased around the business pin
    assert req.headers["User-Agent"].startswith("restaurante-app/")


async def test_empty_response_is_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    result = await _geocoder(handler).geocode("lugar inexistente")
    assert result is None


async def test_http_error_is_best_effort_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = await _geocoder(handler).geocode("Calle 20")
    assert result is None


async def test_transient_failure_is_not_cached() -> None:
    """A 403 (policy/UA) must not pin the address to a null result for the whole TTL.

    Regression: a placeholder contact in the User-Agent made Nominatim answer 403; the
    failure was cached as a no-match, so every retry returned None for 30 days.
    """
    responses = [httpx.Response(403, text="Access denied."), httpx.Response(200, json=HIT)]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return responses.pop(0)

    geo = _geocoder(handler)
    assert await geo.geocode("Calle 20") is None  # request broke → no pin, nothing cached
    recovered = await geo.geocode("Calle 20")  # retry actually re-hits the transport

    assert calls == 2
    assert recovered is not None
    assert recovered.latitude == Decimal("11.5369275")


async def test_genuine_no_match_is_cached() -> None:
    """An address Nominatim truly has no result for stays cached — no repeat lookups."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[])

    geo = _geocoder(handler)
    assert await geo.geocode("lugar inexistente") is None
    assert await geo.geocode("lugar inexistente") is None
    assert calls == 1  # second call served from the cached miss sentinel


async def test_result_is_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=HIT)

    geo = _geocoder(handler)
    a = await geo.geocode("Calle 20", bias_lat=Decimal("11.54"), bias_lon=Decimal("-72.91"))
    b = await geo.geocode("Calle 20", bias_lat=Decimal("11.54"), bias_lon=Decimal("-72.91"))
    assert a is not None and b is not None
    assert a.latitude == b.latitude
    assert calls == 1  # second call served from cache, no transport hit


# --- Colombian nomenclature: query the street, verify the road -----------------------


def _capture(handler):
    """Run the geocoder, recording every `q` it actually sent."""
    seen: list[str] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params)["q"])
        return handler(request)

    return _geocoder(wrapped), seen


def _hit(road: str, lat: str = "11.5226884", lon: str = "-72.9125593"):
    return [
        {
            "lat": lat,
            "lon": lon,
            "display_name": f"{road}, Divino Niño, Riohacha, La Guajira, Colombia",
            "address": {"road": road, "neighbourhood": "Divino Niño"},
        }
    ]


async def test_the_house_number_is_dropped_from_the_query() -> None:
    """OSM holds Riohacha's streets, not its addressed buildings: `#10-20` matches nothing."""
    geo, seen = _capture(lambda r: httpx.Response(200, json=_hit("Calle 15")))
    result = await geo.geocode("Calle 15 #10-20, Riohacha")

    assert result is not None
    assert seen == ["Calle 15"]  # not the raw address


async def test_a_match_on_a_different_road_is_rejected() -> None:
    """The bug that started this: asked for Calle 41A, Nominatim answered with a house whose
    NUMBER contains "41a", standing on Calle 44. A confident wrong pin beats no pin only for
    the geocoder — never for the driver."""
    geo, seen = _capture(lambda r: httpx.Response(200, json=_hit("Calle 44")))
    result = await geo.geocode("Calle 41B #12C-48")  # 41B has no base-street retry hit

    assert result is None
    assert seen == ["Calle 41B", "Calle 41"]  # tried, rejected, fell back, rejected again


async def test_a_letter_suffixed_street_falls_back_to_its_base() -> None:
    """`Calle 41A` isn't in OSM; `Calle 41` is, and the nomenclature puts them side by side."""
    def handler(request: httpx.Request) -> httpx.Response:
        asked = dict(request.url.params)["q"]
        # Nominatim's real behaviour: a fuzzy hit on the wrong road for the suffixed street.
        return httpx.Response(200, json=_hit("Calle 44" if "41A" in asked else "Calle 41"))

    geo, seen = _capture(handler)
    result = await geo.geocode("calle 41A #12C - 48, Riohacha")

    assert result is not None
    assert result.latitude == Decimal("11.5226884")
    assert seen == ["Calle 41A", "Calle 41"]


async def test_the_chain_stops_at_two_requests() -> None:
    """Public Nominatim allows 1 req/s — the chain must not grow past the fallback."""
    geo, seen = _capture(lambda r: httpx.Response(200, json=[]))
    assert await geo.geocode("Calle 41A #12C-48") is None
    assert len(seen) == 2


async def test_the_cross_street_is_never_queried() -> None:
    """`Carrera 12C` exists and verifies cleanly — and sits 1.48 km away, a whole ring band.
    A verified-but-far match is the dangerous kind: nothing downstream can catch it."""
    geo, seen = _capture(lambda r: httpx.Response(200, json=[]))
    await geo.geocode("calle 41A #12C - 48, Riohacha")

    assert not any("12C" in q or "Carrera" in q for q in seen), seen


async def test_a_street_without_a_suffix_is_tried_once() -> None:
    geo, seen = _capture(lambda r: httpx.Response(200, json=[]))
    assert await geo.geocode("Calle 41 #13-15") is None
    assert seen == ["Calle 41"]  # nothing to fall back to


async def test_an_unparseable_address_is_queried_as_written() -> None:
    """Parsing may only ADD resolutions — never take the raw attempt away."""
    geo, seen = _capture(lambda r: httpx.Response(200, json=_hit("Alguna Via")))
    result = await geo.geocode("la casa de la reja verde")

    assert seen == ["la casa de la reja verde"]
    # No street was asked for, so there is nothing to verify against: trust the top hit.
    assert result is not None


async def test_a_verified_result_keeps_its_neighborhood() -> None:
    geo, _ = _capture(lambda r: httpx.Response(200, json=_hit("Calle 15")))
    result = await geo.geocode("Calle 15 #10-20")

    assert result is not None
    assert result.neighborhood == "Divino Niño"
