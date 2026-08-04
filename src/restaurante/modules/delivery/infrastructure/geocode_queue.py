"""The arq side of `GeocodeQueue`: announce that one delivery needs a pin.

This is the accelerator, not the record of work. The periodic pass reading
`latitude IS NULL AND btrim(address_text) <> ''` is what guarantees a record gets resolved;
an announcement only decides whether that takes seconds or until the next tick.

That is exactly why everything here fails quietly. Redis being unreachable must never fail an
order — and swallowing is only safe because the pass is still there to catch what was dropped.

`arq` is imported lazily, like `RedisCache` does with `redis`, so the module imports and the
test suite runs without a broker present.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from typing import Any

# The jobs the worker runs. Named here because this is the side that says them.
GEOCODE_DELIVERY_JOB = "geocode_delivery"
# Quoting an already-pinned delivery. Separate from the geocode job because the trigger is
# different: this one fires for a delivery that ARRIVED with coordinates (a GPS order), where
# there is nothing to geocode and therefore nothing that would otherwise announce it.
QUOTE_DELIVERY_JOB = "quote_delivery"

# An announcement gets one attempt and a short leash, because failing it is free: the record
# is already in the sweep's set and the pin arrives at the next pass regardless.
#
# arq's default is 5 retries a second apart, which is right for a worker reconnecting to its
# broker and wrong here — measured, it blocked `create_delivery` for 5.1 s against a dead
# Redis. An operator taking an order would have waited 5 s to gain nothing, which is exactly
# the "request path waits on an external service" this whole line of work removed. So: no
# connection retries, and a ceiling on the wait in case Redis accepts and then stalls.
_CONN_RETRIES = 0
_ANNOUNCE_TIMEOUT_SECONDS = 2.0

_log = logging.getLogger(__name__)


class ArqGeocodeQueue:
    """Implements `GeocodeQueue` over arq on `REDIS_URL`.

    Holds one lazily-created connection pool for the process, since the API announces from a
    request path and must not pay a connect per delivery.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: Any | None = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            arq_connections = importlib.import_module("arq.connections")
            settings = arq_connections.RedisSettings.from_dsn(self._redis_url)
            settings.conn_retries = _CONN_RETRIES
            self._pool = await arq_connections.create_pool(settings)
        return self._pool

    async def announce(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
        """Ask the resolver to pin this delivery now. Never raises.

        A dropped announcement is a latency regression, not a lost pin: the record still has
        an address and no location, so the next periodic pass resolves it. Failing the caller
        here would trade that for a failed order, which is a far worse deal.
        """
        await self._enqueue(GEOCODE_DELIVERY_JOB, tenant_id, delivery_id)

    async def announce_quote(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
        """Ask the worker to price this already-pinned delivery now. Never raises.

        Same deal as `announce`: an accelerator, not the record of work. The minute-by-minute
        sweep still reads `quote_status = 'pending_quote'`, so a dropped announcement costs the
        customer up to a tick — not a price.
        """
        await self._enqueue(QUOTE_DELIVERY_JOB, tenant_id, delivery_id)

    async def _enqueue(self, job: str, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
        try:
            async with asyncio.timeout(_ANNOUNCE_TIMEOUT_SECONDS):
                pool = await self._get_pool()
                await pool.enqueue_job(job, str(tenant_id), str(delivery_id))
        except Exception:  # noqa: BLE001 - an announcement may never fail its caller
            _log.warning(
                "Could not announce delivery %s for %s; the periodic pass will handle it.",
                delivery_id,
                job,
                exc_info=True,
            )

    async def close(self) -> None:
        """Release the pool. For a process that shuts down cleanly; safe to skip."""
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
