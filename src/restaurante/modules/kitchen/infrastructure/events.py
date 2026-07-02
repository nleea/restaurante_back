"""Redis pub/sub adapter for live kitchen (KDS) board events.

One channel per tenant/branch (``kds:{tenant_id}:{branch_id}``) so a board only
ever receives its own branch's traffic. Publishing is strictly best-effort: a
broker outage is logged and swallowed — ticket mutations must never depend on
Redis being up. `redis` is imported lazily (mirroring `shared/cache/redis.py`)
so the module imports even where the package is absent.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from restaurante.modules.kitchen.domain.entities import KitchenEvent

logger = logging.getLogger(__name__)

# Keep connection attempts short: a down broker must cost milliseconds, not request time.
_CONNECT_TIMEOUT_S = 0.5
_HEARTBEAT_S = 15.0


def channel_for(tenant_id: uuid.UUID, branch_id: uuid.UUID) -> str:
    return f"kds:{tenant_id}:{branch_id}"


def _event_payload(event: KitchenEvent) -> str:
    return json.dumps(
        {
            "type": event.type,
            "branch_id": str(event.branch_id),
            "station_id": str(event.station_id),
            "ticket_id": str(event.ticket_id),
            "status": event.status,
            "order_id": str(event.order_id) if event.order_id else None,
        }
    )


def _new_client(url: str) -> Any:
    redis_asyncio = importlib.import_module("redis.asyncio")
    return redis_asyncio.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_CONNECT_TIMEOUT_S,
    )


class RedisKitchenEventPublisher:
    """Implements the `KitchenEventPublisher` port over Redis pub/sub."""

    def __init__(self, url: str) -> None:
        self._client: Any = _new_client(url)

    async def publish(self, event: KitchenEvent) -> None:
        try:
            await self._client.publish(
                channel_for(event.tenant_id, event.branch_id),
                _event_payload(event),
            )
        except Exception:  # noqa: BLE001 - best-effort by contract of the port
            logger.warning(
                "kitchen event publish failed (type=%s ticket=%s)",
                event.type,
                event.ticket_id,
                exc_info=True,
            )


class RedisKitchenEventStream:
    """Server side of the SSE endpoint: yields a branch's events as SSE frames.

    Emits a heartbeat comment every ~15 s so proxies keep the connection open —
    including when Redis is unreachable, in which case the stream degrades to
    heartbeats only and the board silently lives on its polling fallback.
    """

    def __init__(self, url: str) -> None:
        self._url = url

    async def frames(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> AsyncIterator[str]:
        pubsub: Any = None
        try:
            try:
                pubsub = _new_client(self._url).pubsub()
                await pubsub.subscribe(channel_for(tenant_id, branch_id))
            except Exception:  # noqa: BLE001 - degrade to heartbeats-only
                logger.warning("kitchen event stream: Redis unavailable", exc_info=True)
                pubsub = None

            while True:
                if pubsub is None:
                    await asyncio.sleep(_HEARTBEAT_S)
                    yield ": ping\n\n"
                    continue
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=_HEARTBEAT_S
                    )
                except Exception:  # noqa: BLE001 - broker dropped mid-stream
                    logger.warning("kitchen event stream: subscription lost", exc_info=True)
                    pubsub = None
                    continue
                if message is None:
                    yield ": ping\n\n"
                elif message.get("type") == "message":
                    yield f"data: {message['data']}\n\n"
        finally:
            if pubsub is not None:
                try:
                    await pubsub.close()
                except Exception:  # noqa: BLE001 - already tearing down
                    pass
