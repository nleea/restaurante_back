"""Shared realtime primitive: topic-scoped, per-tenant/branch event fan-out.

Generalises the KDS live-board pattern (`modules/kitchen/infrastructure/events.py`)
into a reusable building block any module can lean on:

- `EventPublisher` — the outbound port a use case depends on. Best-effort by
  contract: publishing never raises, so a broker outage can never fail a mutation.
- `NullEventPublisher` — the no-op used when Redis isn't configured (dev/tests).
- `RedisEventPublisher` / `RedisEventStream` — the Redis pub/sub adapter and the
  server side of an SSE endpoint, both keyed by ``rt:{topic}:{tenant}:{branch}``.

The composition root (`shared/realtime/deps.py`) picks Redis vs. Null from the same
`cache_backend` switch the cache layer uses, and exposes shared FastAPI deps so a
module router mounts an events stream in a couple of lines.
"""

from __future__ import annotations

from restaurante.shared.realtime.ports import EventPublisher
from restaurante.shared.realtime.publisher import NullEventPublisher
from restaurante.shared.realtime.redis import (
    RedisEventPublisher,
    RedisEventStream,
    channel_for,
)

__all__ = [
    "EventPublisher",
    "NullEventPublisher",
    "RedisEventPublisher",
    "RedisEventStream",
    "channel_for",
]
