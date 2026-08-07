"""Composition root + FastAPI helpers for the shared realtime primitive.

`get_event_publisher()` returns a process-wide publisher chosen by the SAME
`cache_backend` switch the cache layer uses (`shared/cache/__init__.py`): a Redis
adapter in production, a no-op everywhere else. Redis is not a preference here — the
geocoding worker is a separate process, so only a cross-process broker can notify web
streams of a pin it resolved (see `modules/delivery/infrastructure/worker.py`).

`get_event_stream()` builds the SSE server for a request, and `event_stream_response()`
wraps a topic's frames in a `StreamingResponse` so a module router mounts its events
endpoint in a couple of lines behind its own read permission.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.responses import StreamingResponse

from restaurante.shared.config import get_settings
from restaurante.shared.realtime.ports import EventPublisher
from restaurante.shared.realtime.publisher import NullEventPublisher
from restaurante.shared.realtime.redis import RedisEventPublisher, RedisEventStream

# Process-wide publisher: the Redis client is lazy and the port is best-effort, so sharing one
# instance across requests is safe and avoids a connection pool per request. Mirrors the KDS
# publisher slot; a test swaps this for a recording fake and restores it via monkeypatch.
_event_publisher: EventPublisher | None = None


def get_event_publisher() -> EventPublisher:
    """The shared publisher: Redis when `cache_backend == "redis"`, else a no-op.

    Reused by the delivery service, the orders service, and the geocoding worker, so all
    four announce onto the same broker with the same channel scheme.
    """
    global _event_publisher
    if _event_publisher is None:
        settings = get_settings()
        if settings.cache_backend == "redis":
            _event_publisher = RedisEventPublisher(settings.redis_url)
        else:
            _event_publisher = NullEventPublisher()
    return _event_publisher


def get_event_stream() -> RedisEventStream:
    """A per-request SSE server. Cheap to build (stores a URL); degrades to heartbeats
    when Redis is down, so it is safe even where `cache_backend` is `memory`."""
    return RedisEventStream(get_settings().redis_url)


def event_stream_response(
    stream: RedisEventStream,
    topic: str,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> StreamingResponse:
    """Wrap a topic+branch's frames in an SSE `StreamingResponse`.

    The reusable half of an events endpoint: a module router supplies its topic and its
    own read-permission dependency, this supplies the heartbeats, headers and framing.
    """
    return StreamingResponse(
        stream.frames(topic, tenant_id, branch_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


EventStreamDep = Annotated[RedisEventStream, Depends(get_event_stream)]
