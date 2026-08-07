## Why

Operational views (dispatch board, coverage map, salón) don't update when data changes elsewhere: add a delivery and the dispatch board won't show it until a manual refresh; a table/order changes and other open screens go stale. These screens stay open all shift — nobody is going to refresh them. The kitchen (KDS) already solved this with SSE + Redis pub/sub + a polling fallback, but that machinery is kitchen-specific. We want the same live behavior across Delivery and Salón without copy-pasting the pattern four times — and a foundation the upcoming `driver-live-location` change can ride on.

## What Changes

- Extract the KDS realtime pattern into a **shared, topic-based primitive**: a generic per-tenant/branch event publisher over Redis pub/sub and a generic SSE stream, both best-effort (a broker outage never fails a mutation and never breaks a screen — it degrades to the polling fallback).
- A reusable **frontend composable** (`useLiveRefetch`) that captures the KDS store's proven model: SSE event = a *doorbell* that triggers a **debounced refetch**, with **polling always on** as a safety net (relaxed while the stream is healthy, full cadence when it drops).
- **Delivery** publishes events on its mutations (create/assign/depart/mark/finish/open, and the geocoding worker resolving a pin) and exposes a stream; the dispatch board, coverage map, and driver view refetch live.
- **Salón / orders** publishes events on order and table changes and exposes a stream; the floor updates live.
- Kitchen keeps working unchanged (optional later migration onto the shared primitive; out of scope here).

## Capabilities

### New Capabilities
- `realtime-events`: a shared server-side realtime primitive — a best-effort, per-tenant/branch event publisher over Redis pub/sub keyed by a topic, and a generic SSE stream endpoint that a subscribed browser consumes; degrades to heartbeats-only when the broker is down.
- `frontend-realtime`: a reusable client that turns a stream into live updates — the SSE doorbell + debounced refetch + always-on polling fallback — applied to the Delivery (dispatch, coverage map, driver) and Salón views.

### Modified Capabilities
- `delivery-management`: delivery and run mutations (and the geocoding worker resolving a pin) publish a `delivery` realtime event; a delivery events stream is exposed under `delivery.read`.
- `order-management`: order and table changes publish an `orders` realtime event; an orders events stream is exposed under `orders.read`.

## Impact

- **Backend** — new `shared/realtime/` (port `EventPublisher.publish(topic, tenant_id, branch_id, payload)`, `RedisEventPublisher` adapter on channel `rt:{topic}:{tid}:{bid}`, generic `RedisEventStream.frames(topic, …)`, and a FastAPI `StreamingResponse` helper with tenant/branch/permission deps). Delivery use cases (`modules/delivery`) + the geocoding worker publish `delivery` events and mount `GET /delivery/events`. Orders use cases (`modules/orders`) publish `orders` events and mount `GET /orders/events`. Wiring in the composition root; Redis is already a dependency (cache + geocoding), and is required here because the geocoding worker is a **separate process** — only a cross-process broker can notify web streams.
- **Frontend** (`front/src`) — `lib/sse.ts` reused; new `composables/useLiveRefetch.ts` extracted from the KDS store's SSE+poll+debounce logic; wired into `stores/dispatch.ts`, the coverage-map view, `stores/driver.ts`, and the orders/floor store. Events are thin doorbells → refetch (no partial-state application).
- **Out of scope** — Caja (later), migrating kitchen onto the primitive (later), and "fat" position events (deferred to `driver-live-location`, which will depend on this foundation).
- Per-branch channel isolation and multi-tenant safety preserved; English identifiers, Spanish only in UI copy.
