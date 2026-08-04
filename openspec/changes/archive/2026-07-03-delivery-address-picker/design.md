# Design: delivery-address-picker

## Context

`order_deliveries` carries nullable `latitude/longitude` (Numeric 10,7) and
`PATCH /delivery/deliveries/{id}` (`UpdateDeliveryAddressRequest`) already accepts them — but
the dispatch board's "Nuevo domicilio" modal (`views/DispatchView.vue`, since
`dispatch-board-redesign`) only sends `address_text` + `neighborhood` (+ `notes`), and the
frontend `updateDelivery` patch type omits coordinates. The coverage map (`/delivery`, change
`delivery-map-live-orders`) plots open deliveries with coordinates and counts the rest as "sin
ubicación". User context: Riohacha — pick-on-map and WhatsApp-shared locations beat geocoding
there (decided in exploration; geocoding deferred as a possible later *assist*, never the
source of truth).

## Goals / Non-Goals

**Goals:**

- Capture coordinates at delivery creation (map tap or pasted share) and after the fact from
  the delivery detail; both optional and gated like the rest of the form (`delivery.manage`).
- A pasted WhatsApp/Google-Maps location resolves to the same confirmed point a tap produces.
- Deliveries visibly show whether they carry a point (list/detail hint), closing the loop with
  the map's "sin ubicación" count.

**Non-Goals:**

- No geocoding service (address text stays human-facing).
- No backend changes; no changes to `/delivery`'s map beyond what it already reads.
- No customer-facing location links.

## Decisions

- **D1 — Pure parser `parseSharedLocation(text)`** (in `lib/geo.ts`, unit-tested): accepts
  `"lat, lng"` decimal pairs and the Google Maps URL shapes WhatsApp shares produce
  (`.../@lat,lng,...`, `?q=lat,lng`, `?q=loc:lat,lng`, `!3dlat!4dlng` segments); validates
  ranges (lat −90..90, lng −180..180); returns `[lat, lng] | null`. Short-link
  (`maps.app.goo.gl`) redirects can't be resolved client-side — the parser returns null and the
  UI copy tells the operator to open the link and copy the coordinates or long URL.
- **D2 — One reusable `components/dispatch/LocationPickerMap.vue`**: small Leaflet map (reuses
  the existing CDN loader), props `modelValue: [lat,lng] | null` + `center` (branch pin from
  delivery settings; falls back to the country view), emits on tap; shows the candidate marker.
  Used by the board's "Nuevo domicilio" modal and the detail pane's "Agregar/corregir
  ubicación" flow (the `components/dispatch/` folder is recreated for it). The business-pin
  onboarding stays as-is (different semantics), but both share the loader and marker styles.
- **D3 — Form integration**: the "Nuevo domicilio" modal gains a collapsed "Ubicación en el
  mapa (opcional)" section: paste field + mini-map; a parsed paste pans the map and sets the
  candidate point (tap can adjust after). Create sends `latitude/longitude` (7-decimal strings)
  only when a point exists. The board's right detail pane shows "Sin ubicación" with an
  affordance to open the same picker in a small dialog and PATCH.
- **D4 — Service type fix**: `updateDelivery`'s patch type gains
  `latitude?: string; longitude?: string` (backend already accepts them).

## Risks / Trade-offs

- [Operator taps the wrong block] → the point is always visible and editable after the fact
  (D3's detail flow); dots on the coverage map make errors obvious.
- [Short links don't parse] → explicit copy guides the operator; full URLs and raw pairs cover
  the common WhatsApp path.
- [Mini-map inside a PrimeVue Dialog needs size invalidation] → call `invalidateSize` after the
  dialog opens (known Leaflet-in-modal pitfall).

## Migration Plan

Frontend-only, single commit; revert restores the current form. Existing deliveries gain
locations lazily through the detail flow.

## Open Questions

None. (Geocoding-as-assist noted as possible future work, out of scope.)
