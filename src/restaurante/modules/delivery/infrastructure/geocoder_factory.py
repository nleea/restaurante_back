"""How a `Geocoder` gets built from settings — in one place, for both callers.

The API wires one per request; the sweeper (`scripts/geocode_pending`) wires one per pass.
They must agree: a sweeper that resolved addresses differently from the API would write pins
nobody could explain.
"""

from __future__ import annotations

from restaurante.modules.delivery.domain.ports import Geocoder
from restaurante.modules.delivery.infrastructure.corner_geocoder import CornerGeocoder
from restaurante.modules.delivery.infrastructure.geocoder import NominatimGeocoder
from restaurante.modules.delivery.infrastructure.overpass import OverpassCornerLookup
from restaurante.shared.cache import get_cache
from restaurante.shared.config import get_settings


def build_geocoder() -> Geocoder | None:
    """The configured geocoder, or None when geocoding is disabled."""
    settings = get_settings()
    if settings.geocoder_provider != "nominatim":
        return None
    cache = get_cache()
    nominatim = NominatimGeocoder(
        cache,
        base_url=settings.nominatim_url,
        user_agent=settings.nominatim_user_agent,
        cache_ttl_seconds=settings.geocode_cache_ttl_seconds,
    )
    if not settings.overpass_url:
        # Corners switched off: the street-level pin is the whole chain.
        return nominatim
    return CornerGeocoder(
        nominatim,
        OverpassCornerLookup(
            cache,
            base_url=settings.overpass_url,
            # Overpass's policy asks for the same thing Nominatim's does: a real contact.
            user_agent=settings.nominatim_user_agent,
            cache_ttl_seconds=settings.overpass_cache_ttl_seconds,
        ),
    )
