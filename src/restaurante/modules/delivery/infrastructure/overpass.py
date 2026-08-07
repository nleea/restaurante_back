"""Overpass: the node two named streets share — i.e. the corner.

Nominatim cannot answer "where do these two streets cross". Asked for `Calle 41 & Carrera 12C`
it returns Carrera 12C's own representative point, 1.48 km from the address; intersecting the
two matches' bounding boxes fails because each box covers one *way*, not the street — for this
address the boxes do not even overlap. Overpass can, because it queries geometry: the node
shared by the ways named `Calle 41` and the ways named `Carrera 12C`.

That answer is worth 555 m of accuracy on the address that prompted this, and it is why this
adapter exists despite Overpass being slow (1.6–9.1 s measured) and unreliable (1 request in 3
returned 504 while probing). Nothing waits on it: the sweeper retries by leaving the row
pin-less. See `openspec/changes/geocode-corner-in-background/design.md`.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

import httpx

from restaurante.modules.delivery.infrastructure.geo_errors import LookupFailed
from restaurante.shared.cache import Cache

_log = logging.getLogger(__name__)

# Overpass plans, then runs. Both are slow here; the ceiling is the server's, not ours.
_TIMEOUT_SECONDS = 30.0
_QUERY_TIMEOUT_SECONDS = 25
# Sentinel cached for a no-match, so a repeated unmappable corner doesn't re-hit Overpass.
_MISS = ""

Corner = tuple[Decimal, Decimal]


class OverpassCornerLookup:
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

    async def corner(self, street: str, cross: str, *, city: str) -> Corner | None:
        """Where `street` crosses `cross` inside `city`, or None when OSM has no such node.

        Raises `LookupFailed` when the lookup itself broke, so a caller can tell "these streets
        do not meet" (cacheable) from "we could not ask" (not cacheable, and common here).
        """
        if not (street.strip() and cross.strip() and city.strip()):
            return None
        key = _cache_key(city, street, cross)
        cached = await self._cache.get(key)
        if cached is not None:
            return _decode(cached)
        result = await self._query(street, cross, city)
        await self._cache.set(key, _encode(result), self._ttl)
        return result

    async def _query(self, street: str, cross: str, city: str) -> Corner | None:
        query = (
            f"[out:json][timeout:{_QUERY_TIMEOUT_SECONDS}];"
            f'area["name"={_quote(city)}]["boundary"="administrative"]->.a;'
            f'way(area.a)["name"={_quote(street)}]->.w1;'
            f'way(area.a)["name"={_quote(cross)}]->.w2;'
            f"node(w.w1)(w.w2);out;"
        )
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": self._user_agent},
                transport=self._transport,
            ) as client:
                resp = await client.post(f"{self._base_url}/api/interpreter", data={"data": query})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            # 504 is the common one: the public instance sheds load rather than queueing, and
            # it did so on 1 of 3 probe requests. 429 is the rate limiter. Both are transient.
            raise LookupFailed(
                f"{exc.response.status_code} from {self._base_url}: " f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - network/timeout/decode: never break a pass
            raise LookupFailed(f"{type(exc).__name__}: {exc}") from exc

        nodes = _nodes(data)
        if not nodes:
            _log.info("No corner in OSM: %r x %r (%s)", street, cross, city)
            return None
        # A divided road shares two nodes with its cross street — `Calle 15 x Carrera 10`
        # returned a pair 18 m apart. Order by node id and take the first: deterministic, and
        # 18 m is far below the precision this feature claims (the corner, not the house).
        _, lat, lon = min(nodes, key=lambda n: n[0])
        return lat, lon


def _nodes(data: object) -> list[tuple[int, Decimal, Decimal]]:
    """The (id, lat, lon) of every node in the response — anything malformed is not a node."""
    if not isinstance(data, dict):
        return []
    elements = data.get("elements")
    if not isinstance(elements, list):
        return []
    nodes: list[tuple[int, Decimal, Decimal]] = []
    for element in elements:
        if not isinstance(element, dict) or element.get("type") != "node":
            continue
        node_id = element.get("id")
        if not isinstance(node_id, int):
            continue
        try:
            nodes.append((node_id, Decimal(str(element["lat"])), Decimal(str(element["lon"]))))
        except (KeyError, InvalidOperation):
            continue
    return nodes


def _quote(value: str) -> str:
    """Overpass QL string literal. The city comes from a provider, so it is not ours to trust."""
    escaped = re.sub(r'(["\\])', r"\\\1", value)
    return f'"{escaped}"'


def _cache_key(city: str, street: str, cross: str) -> str:
    # Sorted: `Calle 41 x Carrera 12C` and `Carrera 12C x Calle 41` are the same corner, and
    # the same request. Overpass is expensive enough to be worth the symmetry.
    a, b = sorted((street.lower(), cross.lower()))
    return f"corner:overpass:{city.lower()}:{a}:{b}"


def _encode(corner: Corner | None) -> str:
    if corner is None:
        return _MISS
    return json.dumps({"lat": str(corner[0]), "lon": str(corner[1])})


def _decode(raw: str) -> Corner | None:
    if raw == _MISS:
        return None
    data = json.loads(raw)
    return Decimal(data["lat"]), Decimal(data["lon"])
