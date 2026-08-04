"""No-op publisher for when no broker is configured (dev boxes, tests).

Selected by the composition root whenever ``cache_backend`` is not ``redis``. With it
wired, every publish call is a cheap return: the system behaves exactly as it did
before realtime existed — mutations succeed, streams emit heartbeats only, and each
view lives on its polling fallback.
"""

from __future__ import annotations

import uuid
from typing import Any


class NullEventPublisher:
    """Implements `EventPublisher` by doing nothing (and never raising)."""

    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        return None
