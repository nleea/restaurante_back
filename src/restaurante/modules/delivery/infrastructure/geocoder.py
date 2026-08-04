"""Geocoder adapters for delivery addresses.

`NominatimGeocoder` turns a written address into an approximate map pin using public
Nominatim (OpenStreetMap), biased to the business location and cached. Best-effort: any
failure returns ``None`` so the caller keeps a null pin (placed manually on the map).
Swappable behind the domain `Geocoder` port (a self-hosted Photon adapter can replace it).

Two things make a real Colombian address resolvable (see `address_co`):

* **Only the street is queryable.** `Calle 41A #12C-48` names a house OSM does not hold, so
  the house number is dropped from the query — and kept in the stored address, which is what
  the driver delivers by.
* **Every match is verified.** Asked for a street it lacks, Nominatim answers with a confident
  wrong match rather than nothing; a pin two barrios away is worse than no pin, because
  nothing downstream can tell. A result whose road isn't the street we asked for is discarded.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

import httpx

from restaurante.modules.delivery.domain.entities import GeoResult
from restaurante.modules.delivery.infrastructure.address_co import (
    parse_street,
    road_matches,
)
from restaurante.modules.delivery.infrastructure.geo_errors import LookupFailed
from restaurante.shared.cache import Cache

_log = logging.getLogger(__name__)

# A ~15 km box around the bias point — enough for a city, tight enough to disambiguate.
_VIEWBOX_DELTA = Decimal("0.15")
_TIMEOUT_SECONDS = 8.0
# Sentinel cached for a no-match, so a repeated unresolvable address doesn't re-hit Nominatim.
_MISS = ""


class NominatimGeocoder:
    def __init__(
        self,
        cache: Cache,
        *,
        base_url: str,
        user_agent: str,
        cache_ttl_seconds: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cache = cache
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._ttl = cache_ttl_seconds
        # Injectable for tests (httpx.MockTransport); None → the default network transport.
        self._transport = transport

    async def geocode(
        self,
        query: str,
        *,
        bias_lat: Decimal | None = None,
        bias_lon: Decimal | None = None,
    ) -> GeoResult | None:
        q = query.strip()
        if not q:
            return None
        # Keyed on the CALLER's address, not the candidate we end up querying: a repeated
        # address costs zero requests whether it resolved or missed.
        key = self._cache_key(q, bias_lat, bias_lon)
        cached = await self._cache.get(key)
        if cached is not None:
            return _decode(cached)
        try:
            result = await self._resolve(q, bias_lat, bias_lon)
        except LookupFailed as exc:
            # A transient failure (network, timeout, 403/5xx) is NOT a "no match": caching it
            # would pin the address to a null pin for the whole TTL. Skip the cache and retry
            # on the next call.
            _log.warning("Geocoding failed for %r: %s", q, exc)
            return None
        await self._cache.set(key, _encode(result), self._ttl)
        return result

    async def reverse_city(self, lat: Decimal, lon: Decimal) -> str | None:
        """The city a point falls in — e.g. the branch's business pin → "Riohacha".

        Overpass scopes its corner query to a *named* administrative area, and branch settings
        hold coordinates, not a city name. This is the bridge. Cached on the point: a branch
        does not move, so this costs one request per branch, ever.

        Unlike `geocode`, a broken lookup RAISES `LookupFailed` rather than answering None.
        The two answers lead somewhere different: no city means "this branch will never get a
        corner, use the street pin", while a failed lookup means "ask again in a minute". Told
        apart here, they would collapse into writing the worse pin permanently.
        """
        key = f"city:nominatim:{lat},{lon}"
        cached = await self._cache.get(key)
        if cached is not None:
            return cached or None
        city = await self._reverse_city(lat, lon)
        # A miss IS cacheable: a point outside any named city stays outside it.
        await self._cache.set(key, city or _MISS, self._ttl)
        return city

    async def _reverse_city(self, lat: Decimal, lon: Decimal) -> str | None:
        params = {
            "lat": str(lat),
            "lon": str(lon),
            "format": "jsonv2",
            "addressdetails": "1",
            # City level. Zooming closer answers with a barrio, which names no OSM boundary
            # Overpass can scope an area to.
            "zoom": "10",
        }
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": self._user_agent},
                transport=self._transport,
            ) as client:
                resp = await client.get(f"{self._base_url}/reverse", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LookupFailed(
                f"{exc.response.status_code} from {self._base_url}: " f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - network/timeout/decode: never break a pass
            raise LookupFailed(f"{type(exc).__name__}: {exc}") from exc
        if not isinstance(data, dict):
            return None
        address = data.get("address") or {}
        city = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("village")
        )
        return city if isinstance(city, str) and city.strip() else None

    async def _resolve(
        self, address: str, bias_lat: Decimal | None, bias_lon: Decimal | None
    ) -> GeoResult | None:
        """Turn a written address into a verified pin, or nothing.

        Colombian nomenclature ("Calle 41A #12C-48") names a house OSM does not hold, so only
        the street is queryable. Each candidate is verified against the road that comes back —
        asked for a street it lacks, Nominatim answers with a confident wrong match rather than
        an empty one, and a wrong pin is worse than none: nothing downstream can tell.

        At most two requests, against a public 1 req/s policy.
        """
        parsed = parse_street(address)
        if parsed is None:
            # Not nomenclature we know. Query it as written — the behaviour that predates the
            # parser — so parsing can only ever ADD resolutions.
            return await self._query(address, bias_lat, bias_lon)

        # "Calle 41A" first; "Calle 41" only if the suffixed street isn't mapped. Never the
        # cross street: its representative point measured 1.48 km away — a whole ring band.
        candidates = [parsed.street]
        if parsed.base_street:
            candidates.append(parsed.base_street)

        for candidate in candidates:
            result = await self._query(candidate, bias_lat, bias_lon, expect_road=candidate)
            if result is not None:
                return result
        return None

    async def _query(
        self,
        q: str,
        bias_lat: Decimal | None,
        bias_lon: Decimal | None,
        *,
        expect_road: str | None = None,
    ) -> GeoResult | None:
        """Return the top match, None when Nominatim has no result — or a wrong one.

        `expect_road` is the street this query is asking for. When given, a result whose
        `address.road` names a different street is discarded: Nominatim would rather answer
        with a fuzzy match on some house number than answer nothing. Omitted for a raw
        fall-through query, where there is no street to compare against.

        Raises `LookupFailed` when the lookup itself broke, so the caller can tell a real
        "this address doesn't exist" (cacheable) from "we couldn't ask" (not cacheable).
        """
        params: dict[str, str] = {
            "q": q,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "1",
            "countrycodes": "co",
        }
        if bias_lat is not None and bias_lon is not None:
            d = _VIEWBOX_DELTA
            # viewbox = lon_min, lat_max, lon_max, lat_min
            params["viewbox"] = f"{bias_lon - d},{bias_lat + d},{bias_lon + d},{bias_lat - d}"
            params["bounded"] = "1"
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": self._user_agent},
                transport=self._transport,
            ) as client:
                resp = await client.get(f"{self._base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            # 403 here almost always means the User-Agent breaches the Nominatim usage policy
            # (a placeholder contact is rejected); 429 means rate-limited. Both are transient.
            raise LookupFailed(
                f"{exc.response.status_code} from {self._base_url}: " f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - network/timeout/decode: never break the order
            raise LookupFailed(f"{type(exc).__name__}: {exc}") from exc
        if not data:
            return None
        top = data[0]
        try:
            lat = Decimal(str(top["lat"]))
            lon = Decimal(str(top["lon"]))
        except (KeyError, InvalidOperation):
            return None
        address = top.get("address") or {}
        if expect_road is not None and not road_matches(expect_road, address.get("road")):
            # A fuzzy hit on something else — e.g. asked for "Calle 41A", got a house whose
            # number contains "41a" standing on Calle 44. Discard: a null pin is an honest
            # gap the dispatcher fills; a wrong one is a driver in the wrong barrio.
            _log.info(
                "Geocode rejected: asked %r, road was %r",
                expect_road,
                address.get("road"),
            )
            return None
        neighborhood = (
            address.get("neighbourhood") or address.get("suburb") or address.get("quarter")
        )
        return GeoResult(
            latitude=lat,
            longitude=lon,
            neighborhood=neighborhood,
            display_name=top.get("display_name", ""),
        )

    @staticmethod
    def _cache_key(q: str, bias_lat: Decimal | None, bias_lon: Decimal | None) -> str:
        bias = f"{bias_lat},{bias_lon}" if bias_lat is not None and bias_lon is not None else "-"
        return f"geocode:nominatim:{bias}:{q.lower()}"


def _encode(result: GeoResult | None) -> str:
    if result is None:
        return _MISS
    return json.dumps(
        {
            "lat": str(result.latitude),
            "lon": str(result.longitude),
            "neighborhood": result.neighborhood,
            "display_name": result.display_name,
        }
    )


def _decode(raw: str) -> GeoResult | None:
    if raw == _MISS:
        return None
    data = json.loads(raw)
    return GeoResult(
        latitude=Decimal(data["lat"]),
        longitude=Decimal(data["lon"]),
        neighborhood=data.get("neighborhood"),
        display_name=data.get("display_name", ""),
    )
