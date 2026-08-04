# Proposal: wire-delivery-routes-map

## Why

The "Domicilios" map prototype (`/delivery-routes`, mock data) turned out to be a redesign of a
screen that already exists: `DeliveryView` at `/delivery` manages the same routes, zones and
driver assignments against a real backend — just as text forms, without the map. This change
replaces that screen with the prototype wired to real data, and adds the small backend surface
the map needs: where the business is (ring center), how wide each ring band is, route colors,
structured zones, and a derived driver status.

## What Changes

- **`/delivery` becomes the map view**: routes list + Leaflet ring map + radius configurator +
  slide-in route detail, all backed by the existing `/delivery` API. The old form-based
  `DeliveryView` is retired; the mock `/delivery-routes` route is removed. `/dispatch` (per-order
  lifecycle) is untouched.
- **Branch delivery settings (new)**: per-branch `delivery_settings` — business latitude/
  longitude (the ring center) and `ring_step_km` (uniform band width, per the user's decision) —
  with read/update endpoints. First-run onboarding: the screen asks for the device location as a
  suggestion, and the pin is placed/adjusted by clicking the map; relocatable afterwards.
- **Routes gain map data**: `color` (hex) and `position` (ring band order, backfilled by creation
  order); `covered_zones` free-text migrates to a structured `zones` JSON list (split on commas).
- **Driver status derived, not stored**: route-driver listings expose `on_route` (has an active
  run), `inactive` (assignment inactive), else `available` — powering the prototype's status
  pills from data the dispatch flow already produces.
- Prototype UI keeps its components; only its seed is replaced by store-backed state
  (write-through, same seam pattern as the KDS wiring).

## Capabilities

### New Capabilities

_None — this extends both existing delivery capabilities._

### Modified Capabilities

- `delivery-management`: branch delivery settings (coords + ring step); routes carry color,
  zones list and band position; route-driver listing includes derived status.
- `frontend-delivery`: the route screen becomes the coverage map (rings, radius config, location
  onboarding, colored routes, driver status pills), keeping the same permissions and the same
  assign/remove flows.

## Impact

- **Backend** (`modules/delivery`): new `delivery_settings` model + endpoints, columns
  `color`/`zones`/`position` on `delivery_routes` (Alembic migration with `covered_zones` → 
  `zones` backfill and per-branch position backfill), derived status in the route-drivers
  read path, schema updates, tests.
- **Frontend**: `services/delivery.api.ts` (settings + extended types + driver status),
  `stores/delivery.ts` (settings, extended routes), `lib/deliveryRoutes.ts` (seed confined to
  tests), `views/DeliveryRoutesView.vue` + `components/deliveryroutes/*` (store-backed, location
  onboarding, persisted slider), router (auth-gated `/delivery` swap, `/delivery-routes`
  removed), old `DeliveryView.vue` retired.
- `frontend-delivery-dispatch` and the delivery lifecycle are not touched.
