# Tasks — geocode delivery addresses (Nominatim)

## Backend — the Geocoder port + Nominatim adapter

- [x] 1.1 `Geocoder` protocol + `GeoResult` dataclass in the delivery domain
  (`geocode(query, *, bias_lat, bias_lon) -> GeoResult | None`).
- [x] 1.2 `NominatimGeocoder` adapter (infrastructure): httpx GET `NOMINATIM_URL/search`
  with `format=jsonv2, countrycodes=co, addressdetails=1, limit=1`, a `viewbox` around the
  bias point (± ~0.15°) + `bounded=1`, and a valid `User-Agent`. Parse the top hit →
  `GeoResult` (lat, lon, neighborhood from `address.suburb/neighbourhood/quarter`). Return
  `None` on empty/error; short timeout.
- [x] 1.3 Redis cache in the adapter: key = normalized `(query, bias-city)`, long TTL;
  cache hit skips the network. Reuse the existing redis dependency.
- [x] 1.4 Config in `Settings`: `GEOCODER_PROVIDER=nominatim`, `NOMINATIM_URL`
  (default public), `NOMINATIM_USER_AGENT` (identify the app + contact), `GEOCODE_CACHE_TTL`.
  DI wires the adapter into `DeliveryService` (provider-selected; a no-op/null geocoder when
  disabled).

## Backend — wire geocoding into the delivery write paths

- [x] 2.1 `create_delivery`: when no explicit `latitude`/`longitude` is passed and
  `address_text` is present, geocode (biased to the branch's `DeliverySetting` pin),
  best-effort/non-blocking; set lat/lng and fill `neighborhood` when empty. An explicit pin
  always wins. A geocode failure never fails creation.
- [x] 2.2 `update_delivery_address`: same rule — re-geocode when the address changes and no
  explicit pin is provided; an explicit pin is preserved.

## Backend — tests

- [x] 2.3 Tests with a **fake `Geocoder`** (no network): create with only an address →
  lat/lng + neighborhood filled from the fake; geocoder returns `None` → lat/lng stay null,
  order still created; an explicit pin is never overwritten; editing the address
  re-geocodes. Adapter URL/param building unit-tested with a mocked httpx transport.

## Frontend — paint + fallback (Option B)

- [x] 3.1 Confirm the deliveries overlay paints the order's geocoded `latitude/longitude`
  (already the case) — no geocoding in the browser.
- [x] 3.2 Keep the manual `LocationPickerMap` as the fallback: a missing pin invites a
  manual placement; an approximate pin can be dragged. (Optional: style geocoded-unconfirmed
  pins distinctly — only if trivial.)

## Verification

- [x] 4.1 Backend `pytest` green (new geocode tests, network faked); ruff + mypy.
- [x] 4.2 Frontend `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build` green.
- [ ] 4.3 Live walk (dev): create a delivery order with "Calle 20, Riohacha" → a pin appears
  near Calle 20 with the barrio filled; a nonsense address → no pin, manual picker places it;
  an explicit manual pin is preserved on edit.
