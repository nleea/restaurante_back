## 1. Shared realtime primitive (backend)

- [x] 1.1 Add `shared/realtime/` with a domain port `EventPublisher.publish(topic, tenant_id, branch_id, payload)` (best-effort contract) and a no-op/null publisher for when Redis is absent
- [x] 1.2 `RedisEventPublisher` adapter: publish JSON to channel `rt:{topic}:{tid}:{bid}`; short connect timeout; swallow+log failures (mirror `modules/kitchen/infrastructure/events.py`)
- [x] 1.3 `RedisEventStream.frames(topic, tenant_id, branch_id)`: subscribe + yield SSE frames, ~15s heartbeats, degrade to heartbeats-only when Redis is down, close pubsub in `finally`
- [x] 1.4 A FastAPI helper to build a `StreamingResponse` events endpoint given a topic + tenant/branch/permission deps
- [x] 1.5 Wire the Redis adapter (or null publisher) in the composition root from the existing Redis/cache config; expose a shared dependency
- [x] 1.6 Tests: publisher no-ops without Redis and never raises; stream degrades to heartbeats; per-topic/branch channel isolation

## 2. Delivery realtime (backend)

- [x] 2.1 Inject the `EventPublisher` into `DeliveryService`; publish a `delivery` event (branch-scoped, small kind: created/status/pin) after create/assign/depart/mark/finish/open-my-run/unassign
- [x] 2.2 Publish a `delivery` event from the geocoding worker when it resolves a pin (separate process → proves the cross-process path)
- [x] 2.3 Mount `GET /delivery/events?branch_id=…` under `delivery.read` using the shared stream helper
- [x] 2.4 Tests: mutations publish (with a fake publisher), a broker failure doesn't fail the mutation, the stream endpoint requires `delivery.read`

## 3. Orders/Salón realtime (backend)

- [x] 3.1 Inject the `EventPublisher` into the orders use cases; publish an `orders` event (branch-scoped) on order created/updated/items/closed/cancelled and dining-table status changes
- [x] 3.2 Mount `GET /orders/events?branch_id=…` under `orders.read` using the shared stream helper
- [x] 3.3 Tests: order/table mutations publish; broker failure is non-fatal; stream requires `orders.read`

## 4. Frontend composable

- [x] 4.1 Add `composables/useLiveRefetch({ url, onDoorbell, pollFull, pollRelaxed, debounceMs })`, extracting the KDS store's SSE-doorbell + debounced-refetch + polling-fallback + lifecycle (reuse `lib/sse.ts`)
- [x] 4.2 Guard against stale clients and clear timers/connection on stop (as the kitchen store does)
- [x] 4.3 (Optional) refactor `stores/kitchen.ts` to use the composable, or leave it untouched — keep KDS behavior identical either way

## 5. Frontend wiring

- [x] 5.1 Dispatch board: subscribe `stores/dispatch.ts` to `/delivery/events` → refetch deliveries/runs live
- [x] 5.2 Coverage map (`DeliveryRoutesView`): subscribe to `/delivery/events` → refresh delivery drops live (incl. worker pin resolution)
- [x] 5.3 Driver view: subscribe `stores/driver.ts` to `/delivery/events` → refresh my run when it changes from the dispatcher side
- [x] 5.4 Salón/floor: subscribe the orders/floor store to `/orders/events` → refresh tables/orders live

## 6. Verify

- [x] 6.1 Backend quality gate: ruff, mypy, pytest green
- [x] 6.2 Frontend quality gate: type-check, lint, build green
- [x] 6.3 Live check with Redis: add a delivery in one client → it appears on the dispatch board and coverage map without refresh; an order/table change appears on the floor
- [x] 6.4 Fallback check: with Redis down, mutations still succeed and views keep updating on polling
- [x] 6.5 Note in `driver-live-location` that it now depends on this foundation (fat position events ride the same transport)
