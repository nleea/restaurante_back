# Design — geocode delivery addresses (Nominatim)

## Context

- `OrderDeliveryModel` already has `address_text` (required), `neighborhood` (nullable),
  `latitude`/`longitude` (nullable). The pin is set today only by the manual map picker
  (`LocationPickerMap.vue`). The map paints order pins from these fields.
- `DeliverySettingModel` holds the branch's business pin (`latitude`/`longitude`) — the map
  center and the natural bias origin for geocoding.
- `create_delivery(address_text, neighborhood, latitude, longitude)` and
  `update_delivery_address(...)` are the two write paths.
- Backend already depends on `httpx` and `redis`.

Spike (public Nominatim, Riohacha): 7/8 streets resolved with distinct coordinates and
their barrio; Calle 20 vs Calle 40 ~1.5 km apart. Street-level approximation is viable on
OSM data as-is. The one miss ("Avenida Primera") was a colloquial name — the upstream LLM
normalizes to "Calle/Carrera N".

## Decision 1 — a swappable `Geocoder` port

```
delivery/domain/ports.py
  class Geocoder(Protocol):
      async def geocode(self, query: str, *, bias_lat, bias_lon) -> GeoResult | None

  @dataclass
  class GeoResult:
      latitude: Decimal
      longitude: Decimal
      neighborhood: str | None
      display_name: str
```

- `NominatimGeocoder` (infrastructure): httpx GET to `NOMINATIM_URL/search` with
  `format=jsonv2, countrycodes=co, addressdetails=1, limit=1`, a `viewbox` around
  `(bias_lat, bias_lon)` (± ~0.15° ≈ ~15 km) and `bounded=1`, a valid `User-Agent`. Parses
  the top hit into `GeoResult`; extracts `neighborhood`/`suburb`/`quarter` from
  `addressdetails`. Returns `None` on no result / error (best-effort).
- A later `PhotonGeocoder` implements the same port; selected by `GEOCODER_PROVIDER`.
- The port lives in the delivery domain; the use case depends on the protocol, so tests
  inject a fake and the real network is never hit in CI.

## Decision 2 — Redis cache + policy compliance

Nominatim's public policy: ≤1 req/s, valid `User-Agent`, no bulk. We geocode once per
order (not per keystroke) and cache in Redis keyed by the normalized query
(lowercased/trimmed + bias city), TTL long (streets don't move). Cache hits skip the
network entirely. Given low volume + cache, a hard throttle isn't required for the pilot; a
simple per-process serialize (or a Redis token) can be added if volume grows. The cache is
a cross-cutting infra helper (the adapter owns it), not a domain concern.

## Decision 3 — geocode on create + address edit, best-effort, pin-respecting

In `create_delivery` and `update_delivery_address`: **only when no explicit
`latitude`/`longitude` is provided**, call the geocoder with `address_text` biased to the
branch's `DeliverySetting` pin; if it returns a result, set `latitude`/`longitude` and fill
`neighborhood` when empty. If it returns `None` or raises, proceed with a null pin — never
fail the order over geocoding (mirrors the kitchen-routing best-effort pattern). An
explicit pin from the manual picker always wins and is never overwritten by geocoding.

`GET`/re-geocode: editing the address re-geocodes (unless an explicit pin is passed).

## Decision 4 — frontend only paints; manual picker is the fallback (Option B)

No geocoding in the browser. The deliveries overlay paints the order's `latitude/longitude`
(already the case). When a pin is missing (geocode miss), the operator uses the existing
`LocationPickerMap` to place it; when it's approximate/wrong, they can drag it. Optionally,
approximate (geocoded, unconfirmed) pins could be styled differently from
manually-confirmed ones — a small nicety, out of scope unless wanted.

## Risks

- **Nominatim availability / latency.** External dependency; the best-effort wrapper + a
  short timeout keep it from blocking order creation. Cache absorbs repeats. The swappable
  port lets us move to self-hosted Photon if the dependency becomes a problem.
- **Policy.** Respect the `User-Agent` + rate via cache/low volume. Document the contact in
  the UA string.
- **Wrong-city / wrong-street match.** The `viewbox` + `countrycodes=co` bias constrains to
  the branch city; the manual picker corrects the rest.
- **Tests must not hit the network.** The `Geocoder` port is faked in tests; the httpx
  adapter is tested in isolation with a mocked transport (or not at all in CI).
