"""Ports (interfaces) of the shared realtime primitive."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class EventPublisher(Protocol):
    """Outbound port: broadcast a small change notification to live browser streams.

    Events are thin doorbells — a topic, a tenant/branch scope, and a coarse payload
    the client uses to decide *what to refetch*, never the new state itself.

    Implementations MUST be best-effort: a broker outage is the publisher's problem
    (log and swallow), never the caller's. `publish` therefore never raises.
    """

    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None: ...
