"""Redis pub/sub adapter for the shared realtime primitive.

One channel per topic + tenant + branch (``rt:{topic}:{tenant_id}:{branch_id}``) so a
subscribed browser only ever receives its own branch's traffic for the surface it is
watching. Publishing is strictly best-effort: a broker outage is logged and swallowed —
mutations must never depend on Redis being up. `redis` is imported lazily (mirroring
`shared/cache/redis.py` and the KDS adapter) so the module imports even where the
package is absent.

This is the generalisation of `modules/kitchen/infrastructure/events.py`: the same care
(short connect timeout, ~15 s heartbeats, degrade-to-heartbeats-only, close the pubsub in
`finally`) with a `topic` parameter added so any module can reuse it.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# Keep connection attempts short: a down broker must cost milliseconds, not request time.
_CONNECT_TIMEOUT_S = 0.5
_HEARTBEAT_S = 15.0


def channel_for(topic: str, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> str:
    return f"rt:{topic}:{tenant_id}:{branch_id}"


def _new_client(url: str) -> Any:
    redis_asyncio = importlib.import_module("redis.asyncio")
    return redis_asyncio.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_CONNECT_TIMEOUT_S,
    )


class RedisEventPublisher:
    """Implements the `EventPublisher` port over Redis pub/sub."""

    def __init__(self, url: str) -> None:
        self._client: Any = _new_client(url)

    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        try:
            await self._client.publish(
                channel_for(topic, tenant_id, branch_id),
                json.dumps(payload),
            )
        except Exception:  # noqa: BLE001 - best-effort by contract of the port
            logger.warning(
                "realtime event publish failed (topic=%s branch=%s)",
                topic,
                branch_id,
                exc_info=True,
            )


class RedisEventStream:
    """Server side of an SSE endpoint: yields a topic+branch's events as SSE frames.

    Emits a heartbeat comment every ~15 s so proxies keep the connection open —
    including when Redis is unreachable, in which case the stream degrades to
    heartbeats only and the view silently lives on its polling fallback.
    """

    def __init__(self, url: str) -> None:
        self._url = url

    async def frames(
        self, topic: str, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> AsyncIterator[str]:
        pubsub: Any = None
        try:
            try:
                pubsub = _new_client(self._url).pubsub()
                await pubsub.subscribe(channel_for(topic, tenant_id, branch_id))
            except Exception:  # noqa: BLE001 - degrade to heartbeats-only
                logger.warning(
                    "realtime stream (topic=%s): Redis unavailable", topic, exc_info=True
                )
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
                    logger.warning(
                        "realtime stream (topic=%s): subscription lost",
                        topic,
                        exc_info=True,
                    )
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
