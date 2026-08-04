"""Ports (interfaces) of the shared storage."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class StorageGateway(Protocol):
    """Outbound port: store and retrieve arbitrary binary blobs.

    Implementations MUST be best-effort: a storage outage is the storage's problem
    (log and swallow), never the caller's. `store` therefore never raises.
    """
    
    @property
    def is_configured(self) -> bool: ...

    async def presign_put(
        self, key: str, *, 
        now: datetime, 
        expires_seconds: int = 300
    ) -> None: ...

    async def public_url(
        self,
        key: str,
    ) -> bytes | None: ...
