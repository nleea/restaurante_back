# Geocode delivery addresses (Nominatim) to place orders on the map

## Why

A delivery order carries a written address (`OrderDelivery.address_text`, e.g. "Calle 14F
#21-71") but its map pin (`latitude`/`longitude`) is only ever set **by hand** via the
map picker. Orders will increasingly arrive through an LLM-assisted flow that produces a
clean street ("Calle 20", "Carrera 15"), so the address can be turned into an approximate
map pin automatically — the operator just wants the order to *show up on the map* near the
right street, not door-level precision or routing.

A quick feasibility spike against public Nominatim confirmed OSM has Riohacha's streets and
distinguishes them (Calle 20 and Calle 40 resolve ~1.5 km apart, each with its barrio). So
street-level approximation is achievable today, for free, with no new data.

## What Changes

**Backend only** — the frontend does not geocode; it only paints the pin.

- **A `Geocoder` port** in the delivery module with a **`NominatimGeocoder` adapter**
  (httpx → public Nominatim). The adapter is **swappable** (a `PhotonGeocoder` can replace
  it later behind the same port with only a config change).
- **Biased to the business's city.** The query is constrained with `countrycodes=co` and a
  `viewbox` built around the branch's delivery-settings pin (`DeliverySetting.lat/lng`), so
  "Calle 20" resolves in Riohacha, not another city. Returns lat/lon + the barrio.
- **Cached in Redis** by normalized address (long TTL — streets don't move), which also
  keeps usage within Nominatim's policy (≤1 req/s) alongside a valid `User-Agent`.
- **Wired into delivery creation and address edits.** `create_delivery` and
  `update_delivery_address`, when **no explicit pin is provided**, geocode `address_text`
  (best-effort, non-blocking) and store the result in the order's existing
  `latitude`/`longitude` (and fill `neighborhood` when empty). A geocoding failure never
  fails the order — the pin simply stays null.
- **Fallback stays (Option B).** When geocoding misses (street not in OSM) or the pin is
  wrong, the existing manual map picker remains the way to place/adjust the pin. The map
  paints whatever pin the order has; a missing pin invites a manual placement.
- **Config** via `Settings`: `GEOCODER_PROVIDER=nominatim`, `NOMINATIM_URL`,
  `NOMINATIM_USER_AGENT`, geocode cache TTL.

No migration — `OrderDelivery.latitude/longitude/neighborhood` already exist; the geo is
already associated with the order structurally. This change only *populates* them by
geocoding instead of only by hand.

## Impact

- Specs: `delivery-management` (geocode on create/update-address), `frontend-delivery`
  (pins are geocoded server-side; manual adjust remains).
- Backend: new `Geocoder` port + `NominatimGeocoder` adapter (httpx + Redis cache), wired
  into `create_delivery`/`update_delivery_address`; DI/config; tests (adapter mocked).
- Frontend: no geocoding; confirm the deliveries overlay paints the geocoded pin and the
  manual picker still lets an operator place/adjust it.

## Out of scope

- Route optimization or any routing (explicitly not wanted).
- Door-level / house-number precision — street-level approximation is the goal.
- The LLM street extraction itself — that lives upstream in the order-taking flow; this
  change geocodes whatever `address_text` it receives.
- Saving an address + confirmed pin on the customer for reuse (a strong future step, but
  deferred).
- Self-hosting Photon — deferred; the swappable port keeps it a one-line change later.
