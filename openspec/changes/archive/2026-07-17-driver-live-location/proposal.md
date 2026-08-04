## Why

Once a driver works their own run (Change 1 `driver-self-service-run`), the dispatcher still can't see *where* the driver is — the system stores no driver position at all (only branch and destination pins), and the driver app's "you are here" dot is a hardcoded constant. To coordinate a fleet without a GPS integration, the dispatcher needs to see each active driver on the map, and the driver needs to see their real position among their stops. The user wants the **route trail** (breadcrumb), not just the latest point.

## What Changes

- The driver app captures the driver's live position (browser geolocation) **only while a run is active**, with explicit consent and a clear on/off toggle, throttled to respect battery and the API.
- Captured positions are stored as an **append-only trail** attached to the active run (a sequence of timestamped points), so the whole recorded path is available, not just the last fix.
- New endpoint for the driver to push a position sample for their own run (`delivery.drive` + ownership); the trail dies with the run (finished runs stop accruing points).
- The dispatcher's coverage map gains a **live driver layer**: each active run's trail (polyline) + current position marker + a staleness indicator ("hace X min"), read under `delivery.read`.
- The driver map shows the driver's own live position marker (replacing the mock constant).

## Capabilities

### New Capabilities
- `driver-location`: capture, store, and expose a driver's position trail for an active run — an append-only sequence of timestamped points, pushed by the owning driver and read by the dispatcher, dying with the run.
- `frontend-driver-location`: the driver app's geolocation capture — consent + toggle, watch only during an active run, throttled sampling, and the driver's own live-position marker on their map.

### Modified Capabilities
- `frontend-delivery`: the coverage map gains a live driver layer — each active driver's trail, current marker, and last-seen staleness — so the dispatcher can see the domiciliario.

## Impact

- **Backend** (`modules/delivery`): a new position model/table (`delivery_run_positions`: run_id, latitude, longitude, recorded_at) via migration; a `POST` location endpoint gated by `delivery.drive` + run ownership; the driver read (`GET /delivery/me/run`, from Change 1) and/or run reads expose the caller/branch trails; the dispatcher run/coverage read returns each active run's trail + latest point + timestamp. `delivery.read` reads, `delivery.drive` writes — no new permission.
- **Frontend** (`front/src`): new geolocation composable (`navigator.geolocation.watchPosition`, consent, throttle by time/distance, active-run gate) used by the driver view; the driver `RunMap` renders the real own-position marker; the coverage map (`components/deliveryroutes/*`, `lib/deliveryRoutes.ts`, `DeliveryRoutesView.vue`) renders the driver-trail layer with staleness; updates via polling (or SSE, reusing the KDS realtime pattern).
- **Depends on** Change 1 (`delivery.drive`, driver identity/ownership, the driver view wired to real data).
- **Privacy**: tracking is consented, scoped to an active run, and stops on finish; positions are branch/tenant-scoped like every other delivery record. English identifiers; Spanish only in UI copy.
