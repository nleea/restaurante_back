"""The Overpass corner lookup, against a mocked transport — never the network.

The public instance is slow and sheds load; a suite that called it would be slow and flaky for
the same reasons. Live probes live in the scratchpad, not here.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from restaurante.modules.delivery.infrastructure.geo_errors import LookupFailed
from restaurante.modules.delivery.infrastructure.overpass import OverpassCornerLookup
from restaurante.shared.cache.memory import InMemoryCache


def _lookup(handler) -> OverpassCornerLookup:
    return OverpassCornerLookup(
        InMemoryCache(),
        base_url="https://overpass.test",
        user_agent="tests/1.0",
        cache_ttl_seconds=60,
        transport=httpx.MockTransport(handler),
    )


def _elements(*nodes: dict) -> dict:
    return {"elements": list(nodes)}


def _sent_query(request: httpx.Request) -> str:
    """The Overpass QL the adapter actually posted, out of the form body."""
    return parse_qs(request.content.decode())["data"][0]


class TestCorner:
    @pytest.mark.asyncio
    async def test_the_shared_node_is_the_corner(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_elements(
                    {"type": "node", "id": 1, "lat": 11.5228503, "lon": -72.9117535}
                ),
            )

        corner = await _lookup(handler).corner(
            "Calle 41", "Carrera 12C", city="Riohacha"
        )
        assert corner == (Decimal("11.5228503"), Decimal("-72.9117535"))

    @pytest.mark.asyncio
    async def test_the_query_is_area_scoped_and_names_both_streets(self) -> None:
        """bbox 504'd every time while probing; the area query answered (design §1)."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = _sent_query(request)
            return httpx.Response(200, json=_elements())

        await _lookup(handler).corner("Calle 41", "Carrera 12C", city="Riohacha")
        query = seen["query"]
        assert '["name"="Riohacha"]["boundary"="administrative"]' in query
        assert '"Calle 41"' in query and '"Carrera 12C"' in query
        assert "bbox" not in query

    @pytest.mark.asyncio
    async def test_a_divided_road_shares_two_nodes_so_the_lowest_id_wins(self) -> None:
        """`Calle 15 x Carrera 10` returned a pair 18 m apart — pick one, always the same one."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_elements(
                    {"type": "node", "id": 99, "lat": 11.5, "lon": -72.9},
                    {"type": "node", "id": 42, "lat": 11.6, "lon": -72.8},
                ),
            )

        corner = await _lookup(handler).corner("Calle 15", "Carrera 10", city="Riohacha")
        assert corner == (Decimal("11.6"), Decimal("-72.8"))

    @pytest.mark.asyncio
    async def test_streets_that_do_not_meet_are_a_miss_not_a_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_elements())

        assert await _lookup(handler).corner("Calle 41", "Carrera 99", city="Riohacha") is None

    @pytest.mark.asyncio
    async def test_a_504_is_a_failure_not_a_miss(self) -> None:
        """1 probe request in 3 got this. Caching it would cost the corner for the whole TTL."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(504, text="gateway timeout")

        with pytest.raises(LookupFailed):
            await _lookup(handler).corner("Calle 41", "Carrera 12C", city="Riohacha")

    @pytest.mark.asyncio
    async def test_a_network_error_is_a_failure_not_a_miss(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        with pytest.raises(LookupFailed):
            await _lookup(handler).corner("Calle 41", "Carrera 12C", city="Riohacha")


class TestCaching:
    @pytest.mark.asyncio
    async def test_a_repeated_corner_costs_no_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200, json=_elements({"type": "node", "id": 1, "lat": 11.5, "lon": -72.9})
            )

        lookup = _lookup(handler)
        await lookup.corner("Calle 41", "Carrera 12C", city="Riohacha")
        await lookup.corner("Calle 41", "Carrera 12C", city="Riohacha")
        assert calls == 1

    @pytest.mark.asyncio
    async def test_the_same_corner_named_in_reverse_is_the_same_request(self) -> None:
        """Overpass is expensive enough that the symmetry is worth spending a sort on."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200, json=_elements({"type": "node", "id": 1, "lat": 11.5, "lon": -72.9})
            )

        lookup = _lookup(handler)
        await lookup.corner("Calle 41", "Carrera 12C", city="Riohacha")
        await lookup.corner("Carrera 12C", "Calle 41", city="Riohacha")
        assert calls == 1

    @pytest.mark.asyncio
    async def test_a_miss_is_cached_but_a_failure_is_not(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls <= 2:
                return httpx.Response(504, text="gateway timeout")
            return httpx.Response(200, json=_elements())

        lookup = _lookup(handler)
        for _ in range(2):
            with pytest.raises(LookupFailed):
                await lookup.corner("Calle 41", "Carrera 99", city="Riohacha")
        # The failure was retried, not remembered.
        assert calls == 2
        assert await lookup.corner("Calle 41", "Carrera 99", city="Riohacha") is None
        assert await lookup.corner("Calle 41", "Carrera 99", city="Riohacha") is None
        # ...but the miss was remembered.
        assert calls == 3


class TestQuoting:
    @pytest.mark.asyncio
    async def test_a_city_name_cannot_break_out_of_the_query(self) -> None:
        """The city comes from a provider's response, so it is not ours to trust."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = _sent_query(request)
            return httpx.Response(200, json=_elements())

        await _lookup(handler).corner("Calle 41", "Carrera 12C", city='X"];out;//')
        # The closing quote is escaped, so it stays inside the string literal.
        assert '"X\\"];out;//"' in seen["query"]

    @pytest.mark.asyncio
    async def test_blank_input_asks_nothing(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("should not have been called")

        lookup = _lookup(handler)
        assert await lookup.corner("", "Carrera 12C", city="Riohacha") is None
        assert await lookup.corner("Calle 41", "  ", city="Riohacha") is None
        assert await lookup.corner("Calle 41", "Carrera 12C", city="") is None
