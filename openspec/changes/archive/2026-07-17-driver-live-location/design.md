## Context

Change 1 wires the driver view to real data and adds `delivery.drive` + driver identity/ownership. This change adds the missing spatial dimension: no driver position exists anywhere today (only branch pin in `delivery_settings` and destination pins on `order_deliveries`). The driver map's "Tú" dot is a constant; the dispatcher has no way to see a driver on a map. The user wants the **route trail**, so a single last-position column is insufficient — we need a time series.

The app already has an SSE realtime pattern (KDS) and a Leaflet-from-CDN coverage map (`useLeafletRings`, `DELIVERY_POINT_META`) rendering rings + branch pin + delivery drops.

> **Depends on `realtime-foundation`** (implemented 2026-07-17): the shared topic-based realtime primitive (`shared/realtime/` — `EventPublisher` over Redis pub/sub on `rt:{topic}:{tid}:{bid}`, the generic SSE stream, and the frontend `useLiveRefetch` composable) plus the live `delivery` topic (`GET /delivery/events`). Driver positions ride this same transport — but as **fat** events (the position in the payload, applied directly to the map marker) rather than the thin doorbell→refetch used for CRUD, because GPS is high-frequency. So this change adds a fat-event path (or a dedicated position stream/topic) on top of the existing primitive, not a new transport.

## Goals / Non-Goals

**Goals:**
- Capture a driver's position as an append-only trail while their run is active, with consent and a toggle, throttled.
- Let the dispatcher see each active driver's trail + current point + staleness on the coverage map.
- Show the driver their own real position on their map.

**Non-Goals:**
- Turn-by-turn routing / navigation, ETA computation, geofencing.
- Historical analytics over past days' trails (trail is operational, tied to the active run).
- Continuous background tracking when the app is closed or no run is active.
- A native app / background geolocation — this is a foreground web experience.

## Decisions

### D1 — Store an append-only trail keyed by run, not a last-position column
New table `delivery_run_positions` (`delivery_run_id` FK, `latitude`/`longitude` `Numeric(10,7)`, `recorded_at`, `id`), branch/tenant-scoped like siblings. The "current position" is the latest row; the trail is the ordered set.
- *Why:* the user wants the path, not just the dot; append-only is simple, and rows die with the run's usefulness.
- *Alternatives:* (a) last-position columns on `delivery_runs` — rejected, loses the trail. (b) a denormalized "latest" column **plus** the trail table for fast current-point reads — acceptable optimization, deferred unless reads prove slow.

### D2 — Capture only during an active run, consented, throttled
The driver app requests geolocation permission when a run is active and the driver enables tracking; it `watchPosition`es and pushes a sample throttled by **time and distance** (e.g. ≥ ~15–20 s and ≥ ~25–50 m since the last sent point). Tracking stops on finish, on toggle-off, or when no run is active.
- *Why:* battery, data, and privacy; a trail every few seconds is enough to see movement.
- *Trade-off:* throttling coarsens the path; acceptable for "where is my driver", tunable later.

### D3 — Push endpoint under `delivery.drive` + ownership; reads under `delivery.read`
`POST /delivery/me/run/location` (or `/delivery/runs/{id}/location`) appends a point to the caller's own active run (ownership checked, `delivery.drive`). Dispatcher/coverage reads return each active run's trail + latest point + `recorded_at` under `delivery.read`, branch-scoped. No new permission code.
- *Why:* reuses Change 1's authorization model; writing your own location is a driver action, reading the fleet is a dispatcher read.

### D4 — Dispatcher updates over SSE, as FAT events on a DEDICATED topic (resolved: SSE)
Positions reach the dispatcher over `realtime-foundation`'s SSE primitive, applied **fat** (the payload carries lat/lng/recorded_at and is applied directly to the marker/trail — no refetch), because GPS is high-frequency. They ride a **dedicated topic `driver_position`** (channel `rt:driver_position:{tid}:{bid}`), **not** the `delivery` topic: the dispatch board and driver view subscribe to `delivery` via the thin doorbell→refetch composable, so putting position spam there would trigger a full deliveries refetch on every GPS sample. The coverage map loads the current trails once via the dispatcher read, then subscribes to `GET /delivery/positions/events` and applies each fat event.
- *Why:* SSE (the user's choice) with a separate topic keeps high-frequency positions off the CRUD doorbell; fat events avoid a refetch per sample.
- *Alternatives:* poll (rejected — user chose SSE); reuse the `delivery` topic (rejected — doorbell subscribers would refetch on every position).

### D5 — Rendering: a driver layer on the coverage map; the driver's own trail on their map
Extend the coverage map controller to accept driver-position inputs and draw, per active run, a polyline (trail) + a distinct current marker (labeled with driver name + "hace X min"), styled apart from delivery drops and the branch pin. The driver `RunMap` replaces its constant "Tú" dot with the live `watchPosition` fix **and draws the driver's own accumulated trail** (per the user: "show all in its maps") — built from the local fixes it already has, so no SSE is needed for the driver's own view.
- *Why:* the coverage map is the geographic surface; the driver marker must read as *driver*, not another drop; the driver sees where they've been.

### D6 — Prune on finish; Douglas–Peucker for long trails (resolved)
Positions are **pruned when the run finishes** (the user's choice): `finish_run` deletes the run's `delivery_run_positions`, and the dispatcher read only ever includes active runs — so a finished driver's trail leaves the layer and the table doesn't accrete history. Long trails are simplified with **Douglas–Peucker** on read (bounding the points sent to the dispatcher and drawn), on top of the client-side time+distance throttle.
- *Why:* the trail is operational (tied to the active run), not analytics; D–P keeps a long shift's polyline cheap to send and draw.

## Risks / Trade-offs

- **Permission denied / no signal** → tracking is optional and non-blocking; the driver can still work the run, and the dispatcher shows "sin ubicación / hace X" instead of a stale dot.
- **Stale positions look live** → always render `recorded_at` and de-emphasize (or drop) markers older than a threshold; never imply freshness the data doesn't have.
- **Write volume** (many drivers × frequent samples) → throttle client-side by time+distance; append is cheap; prune/ignore trails of finished runs on read.
- **Privacy** → consented, active-run-only, stops on finish; positions are tenant/branch-scoped and not exposed outside the dispatcher read.
- **Battery** → `watchPosition` with a sane `maximumAge`/throttle; stop the watcher when the tab is hidden for long or the run ends.

## Migration Plan

1. Additive migration: create `delivery_run_positions`. No backfill.
2. Ship the push endpoint (`delivery.drive`) and the dispatcher read (`delivery.read`); both inert until a driver enables tracking.
3. Frontend: geolocation composable + driver own-marker; then the coverage-map driver layer.
4. Rollback: stop the client watcher and hide the driver layer; the table can remain unused; no data contract depends on it elsewhere.

## Open Questions

- Retention: keep trails after a run finishes (for a same-day "Mi día" recap) or prune on finish? (Leaning: keep for the current day, prune older.)
  prune on finish
- Poll interval vs SSE: start with polling; promote to SSE if the fleet grows or latency matters.
  SSE
- Trail simplification for long runs (Douglas–Peucker) — needed, or is client throttling enough?
  pDouglas–Peucker
- Should the driver's own map also show their trail, or just the current point? (Likely just current point for the driver; trail is a dispatcher concern.) show all in its maps
