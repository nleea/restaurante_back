"""The shared realtime primitive: best-effort publishing, topic isolation, degrade-to-heartbeats.

No Redis is contacted: the Redis client factory is monkeypatched for the failure paths, so the
tests prove the *contract* (never raise, degrade cleanly) without a broker on the box.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

import restaurante.shared.realtime.redis as rt_redis
from restaurante.shared.realtime import (
    NullEventPublisher,
    RedisEventPublisher,
    RedisEventStream,
    channel_for,
)

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()


class _ExplodingClient:
    async def publish(self, channel: str, message: str) -> None:
        raise RuntimeError("broker down")


def test_channel_is_isolated_by_topic_tenant_and_branch() -> None:
    other = uuid.uuid4()
    assert channel_for("delivery", TENANT, BRANCH) == f"rt:delivery:{TENANT}:{BRANCH}"
    # Any of topic / tenant / branch differing yields a different channel — no cross-talk.
    assert channel_for("delivery", TENANT, BRANCH) != channel_for("orders", TENANT, BRANCH)
    assert channel_for("delivery", TENANT, BRANCH) != channel_for("delivery", other, BRANCH)
    assert channel_for("delivery", TENANT, BRANCH) != channel_for("delivery", TENANT, other)


async def test_null_publisher_is_a_silent_no_op() -> None:
    # The no-Redis default: publishing changes nothing and never raises.
    await NullEventPublisher().publish("orders", TENANT, BRANCH, {"kind": "created"})


async def test_redis_publisher_swallows_a_broker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rt_redis, "_new_client", lambda url: _ExplodingClient())
    publisher = RedisEventPublisher("redis://unused")
    # Best-effort by contract: a broker that raises must not surface to the caller.
    await publisher.publish("delivery", TENANT, BRANCH, {"kind": "pin"})


async def test_stream_degrades_to_heartbeats_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(url: str) -> Any:
        raise ConnectionError("no redis")

    monkeypatch.setattr(rt_redis, "_new_client", _boom)
    # Shrink the heartbeat so the degraded loop yields immediately instead of after ~15 s.
    monkeypatch.setattr(rt_redis, "_HEARTBEAT_S", 0.01)

    frames = RedisEventStream("redis://unused").frames("delivery", TENANT, BRANCH)
    first = await anext(frames)
    assert first == ": ping\n\n"
    await frames.aclose()
