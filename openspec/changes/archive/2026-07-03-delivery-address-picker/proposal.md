# Proposal: delivery-address-picker

## Why

Deliveries are born without coordinates: the dispatch form captures only free-text address and
neighborhood, so the coverage map's new demand overlay files most orders under "sin ubicación".
Automatic geocoding is a poor fit for Riohacha (Colombian door-number nomenclature geocodes
unreliably in small cities), but two capture methods match how domicilios actually work there:
the person taking the order **taps the point on a map** (the city fits one view and the team
knows it by heart), or the customer **shares their location by WhatsApp** and the operator
pastes it. This change adds both.

## What Changes

- **Pick-on-map in the dispatch delivery form**: the "Nuevo domicilio" modal of the dispatch
  board (`/dispatch`) gains a mini-map (centered on the branch's business pin, reusing the
  delivery settings) where a tap sets the delivery's coordinates — same interaction as the
  business-pin onboarding. Optional: a delivery can still be created without a point.
- **Paste a shared location**: the form accepts a pasted `lat,lng` pair or a Google Maps link
  (the formats WhatsApp location shares produce); a pure parser extracts the coordinates and the
  mini-map shows the point for confirmation.
- **Add location later**: a delivery already created without coordinates (or with wrong ones)
  can get them from the board's detail pane via the same picker (`PATCH /delivery/deliveries/{id}`
  already accepts latitude/longitude; the frontend service just doesn't send them yet).
- **No backend changes** — `order_deliveries.latitude/longitude` and the update endpoint already
  exist. The coverage map picks the dots up with no changes of its own.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `frontend-delivery-dispatch`: delivery creation/editing captures coordinates via map tap or
  pasted shared location; deliveries show whether they carry a point.

## Impact

- **Frontend only**: a small `lib/geo.ts` (pure `parseSharedLocation(text)` parser + tests), a
  reusable mini-map picker component (reuses the CDN Leaflet loader from
  `components/deliveryroutes/useLeafletRings.ts`), `views/DispatchView.vue` (the board's
  "Nuevo domicilio" modal + right detail pane), `services/delivery.api.ts` (`updateDelivery`
  patch type gains latitude/longitude), delivery settings read for the map's initial center.
- `/delivery`'s demand overlay benefits automatically (fewer "sin ubicación").
