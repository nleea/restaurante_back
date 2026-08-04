## Context

The KDS already runs live via SSE + Redis pub/sub with a graceful fallback (`modules/kitchen/infrastructure/events.py`: `KitchenEventPublisher` port + `RedisKitchenEventPublisher` adapter on channel `kds:{tid}:{bid}`; `RedisKitchenEventStream.frames()` for the SSE endpoint; the frontend `lib/sse.ts` fetch-stream client + the kitchen store's SSE-doorbell/debounced-refetch/polling-fallback). The transport decision (SSE, not WebSocket) is settled and proven: updates are one-directional (server→client), commands go over REST, SSE rides plain HTTP with the Bearer fetch-stream client and trivial reconnection. This change generalizes that pattern so Delivery and Salón get the same behavior, and so `driver-live-location` can build on it.

## Goals / Non-Goals

**Goals:**
- One shared, topic-based realtime primitive (backend publisher + stream, frontend composable), so turning on live updates for a view is: publish on mutations + expose a stream + subscribe-and-refetch.
- Delivery (dispatch board, coverage map, driver) and Salón (floor/orders) update live without manual refresh.
- Best-effort everywhere: a Redis outage never fails a mutation and never breaks a screen (it falls back to polling).

**Non-Goals:**
- WebSockets (unneeded; REST carries commands).
- Migrating the kitchen onto the shared primitive (leave the working KDS as-is; optional later).
- "Fat" events that carry entity state and apply without a refetch — deferred to `driver-live-location` for high-frequency GPS.
- Caja realtime (later).

## Decisions

### D1 — Shared topic-based primitive, not per-module copies
Add `shared/realtime/`: a port `EventPublisher.publish(topic: str, tenant_id, branch_id, payload: dict)` (best-effort, swallows broker errors), a `RedisEventPublisher` adapter publishing to channel `rt:{topic}:{tid}:{bid}`, a generic `RedisEventStream.frames(topic, tenant_id, branch_id)` (heartbeats + degrade-to-heartbeats-only), and a FastAPI helper that builds a `StreamingResponse` endpoint given a topic + tenant/branch/permission deps. Modules depend on the port; the composition root injects the Redis adapter.
- *Why:* the KDS code is already this shape minus the `topic` parameter; generalizing removes 4× boilerplate and gives one place to harden (timeouts, heartbeat, isolation).
- *Alternatives:* per-module copy (rejected: duplication); a message-queue/broker abstraction beyond Redis (rejected: Redis is already required and sufficient).

### D2 — Events are thin doorbells; refetch is the source of truth
A `delivery`/`orders` event carries only enough to route a refetch (branch, a coarse kind, maybe an id) — the client reacts by **refetching** through the normal API, debounced. No partial state is applied from the event.
- *Why:* matches the KDS model; correctness comes from the authoritative GET, not from reconstructing state client-side; robust against missed/reordered events.
- *Trade-off:* an event costs a refetch. Debounce collapses bursts; the payload can be coarse. High-frequency streams (GPS) that would refetch too often are the explicit exception, deferred to `driver-live-location` as fat events on the same transport.

### D3 — Frontend `useLiveRefetch` composable
Extract the kitchen store's logic into `composables/useLiveRefetch({ url, onDoorbell, pollFull, pollRelaxed, debounceMs })`: opens the SSE client (`lib/sse.ts`), debounces doorbells into `onDoorbell` (a refetch), runs a polling timer that relaxes while connected and returns to full cadence when the stream drops, and starts/stops with the view. Stores call it on mount/activate and stop on unmount.
- *Why:* one implementation of the tricky part (debounce + fallback cadence + lifecycle), so each store is a few lines.
- *Alternative:* leave the logic in each store (rejected: the kitchen store's care around stale clients and cadence is exactly what shouldn't be re-derived per view).

### D4 — Publish points (where mutations announce)
- **Delivery** (`delivery` topic, branch-scoped): `create_delivery`, `assign_delivery`, `depart_run`, `mark_delivered`, `finish_run`, `open_my_run` (and its pull), driver mark/unassign — each publishes after the write commits. Plus the **geocoding worker** publishes when it resolves a pin (separate process → the reason Redis, not an in-process bus, is mandatory).
- **Orders/Salón** (`orders` topic, branch-scoped): order created/updated/items changed/closed/cancelled, and table status changes.
Publishing is best-effort and after the state change, never inside the transaction's critical path such that a broker hiccup rolls back business data.

### D5 — Stream endpoints and permissions
`GET /delivery/events?branch_id=…` gated by `delivery.read`; `GET /orders/events?branch_id=…` gated by `orders.read`. Each resolves tenant from the host and branch from the query, subscribes to `rt:{topic}:{tid}:{bid}`, and streams frames. Mirrors the existing `GET /kitchen/events` shape.

## Risks / Trade-offs

- **Redis down** → publish is a no-op (logged), streams emit heartbeats only, and every view keeps working on its polling fallback. No mutation fails.
- **Refetch storms** (many events → many GETs) → debounce window + relaxed polling while connected; coarse payloads; per-branch channels bound the blast radius.
- **Cross-process correctness** (web workers + geocoding worker + future runners) → Redis pub/sub fans out across processes; an in-process bus would silently miss the worker's pin resolution. This is why Redis is required, not optional.
- **Auth on the stream** → the fetch-stream client sends the Bearer (already solved in `lib/sse.ts`); a 401 self-heals on reconnect after normal traffic refreshes the token.
- **Leaks / dangling subscriptions** → the stream closes its pubsub in `finally`; the composable stops the client and clears timers on unmount; guard against stale clients (as the KDS store does).

## Migration Plan

1. Add `shared/realtime/` + tests (publisher no-ops without Redis; stream degrades).
2. Wire Delivery: publish points + `GET /delivery/events`; subscribe the dispatch store, coverage-map view, and driver store via `useLiveRefetch`.
3. Wire Salón/orders: publish points + `GET /orders/events`; subscribe the floor/orders store.
4. Ship inert-safe: with no Redis, everything behaves exactly as today (polling only).
5. Rollback: stop mounting the stream endpoints and remove the composable calls; publishers become dead no-ops. No data migration.

## Open Questions

- Event granularity per topic: one coarse "delivery changed" kind, or a few kinds (created / status-changed / pin-resolved) so a view can target its refetch? (Leaning: a small kind enum, still doorbell-only.)
- Should the driver view subscribe to `delivery` (its own run may change from the dispatcher side), or is its own write-through enough until `driver-live-location`? (Leaning: subscribe, cheap.)
- Do we migrate kitchen onto the shared primitive now to avoid two parallel implementations, or leave it and migrate later? (Leaning: leave it; don't destabilize a working board.)
- Heartbeat/debounce/poll constants: reuse the KDS values, or tune per topic?
