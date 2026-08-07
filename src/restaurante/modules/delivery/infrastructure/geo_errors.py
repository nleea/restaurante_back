"""The one distinction every geo provider adapter has to make.

A lookup that *broke* is not a lookup that found nothing. Caching a broken lookup pins the
address to a null pin for the whole TTL; retrying a genuine no-match burns requests against a
1 req/s policy forever. Both adapters (Nominatim, Overpass) owe the caller this difference,
so the exception lives where neither owns it.
"""

from __future__ import annotations


class LookupFailed(Exception):
    """The lookup broke (network/timeout/policy/rate limit) — distinct from a no-match."""
