"""Give a pin to the deliveries that don't have one. Run periodically.

Usage:
    poetry run python -m scripts.geocode_pending [limit]

Taking an order stores the address and returns; this closes the loop afterwards. One bounded
pass: take up to `limit` pin-less deliveries (default 50), resolve them one at a time, exit.

A script, not a task on FastAPI startup — uvicorn with `--workers 4` would run four sweepers,
quadrupling the request rate against services that allow one per second, and the failure would
be a silent ban rather than an error. A script cannot accidentally multiply with the web tier.

It runs with no tenant context and therefore sees every tenant's deliveries. That is what a
sweeper needs; see `PendingGeocoder` and `DeliveryRepository.list_pending_geocode`.

Exit code is 0 whenever the pass ran, including when nothing resolved: a provider being down
is the normal weather here, not a job failure. Read the log for what happened.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Registers every model in Base.metadata (cross-module FKs).
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.delivery.application.use_cases.geocode_pending import (
    PendingGeocoder,
)
from restaurante.modules.delivery.infrastructure.geocoder_factory import build_geocoder
from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.shared.database import SessionFactory

_DEFAULT_LIMIT = 50

_log = logging.getLogger("scripts.geocode_pending")


async def main(limit: int) -> int:
    geocoder = build_geocoder()
    if geocoder is None:
        _log.error("Geocoding is disabled (geocoder_provider); nothing to do.")
        return 1
    async with SessionFactory() as session:
        sweeper = PendingGeocoder(SqlAlchemyDeliveryRepository(session), geocoder)
        await sweeper.run(limit)
    return 0


def _limit_from(argv: list[str]) -> int:
    if not argv:
        return _DEFAULT_LIMIT
    try:
        limit = int(argv[0])
    except ValueError:
        raise SystemExit(f"limit must be a number, got {argv[0]!r}") from None
    if limit < 1:
        raise SystemExit("limit must be at least 1")
    return limit


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    sys.exit(asyncio.run(main(_limit_from(sys.argv[1:]))))
