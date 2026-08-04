## 1. Position storage (backend)

- [x] 1.1 Create `delivery_run_positions` table via Alembic migration (`delivery_run_id` FK, `latitude`/`longitude` `Numeric(10,7)`, `recorded_at`, `id`), tenant/branch-scoped; add the model/entity (short revision id — Postgres `alembic_version` is varchar(32))
- [x] 1.2 Repository methods: append a point; read a run's trail ordered by `recorded_at`; read active runs' trails for a branch (latest point + trail); delete a run's positions (prune)

## 2. Push, publish & read (backend)

- [x] 2.1 `POST /delivery/me/run/location` `{latitude, longitude}` — append a point to the caller's own ACTIVE run (`delivery.drive` + run ownership; reject when the run is not `preparing`/`in_transit`)
- [x] 2.2 On append, publish a **fat** event on topic `driver_position` (payload: run_id, employee_id, latitude, longitude, recorded_at, branch_id) via the `realtime-foundation` `EventPublisher` — best-effort
- [x] 2.3 Dispatcher read `GET /delivery/positions?branch_id=` — active runs' trails + current point + `recorded_at` (`delivery.read`), excluding non-active runs; simplify each trail with **Douglas–Peucker**
- [x] 2.4 `GET /delivery/positions/events?branch_id=` — SSE stream of the `driver_position` topic (`delivery.read`), reusing the shared stream helper
- [x] 2.5 Prune on finish: `finish_run` deletes the run's `delivery_run_positions`
- [x] 2.6 Tests: append to own active run succeeds + publishes; append to another driver's run or a finished run is rejected; push without `delivery.drive` is 403; dispatcher read/stream require `delivery.read` and return only active runs; finish prunes the trail

## 3. Driver geolocation capture (frontend)

- [x] 3.1 Geolocation composable: `watchPosition` with consent + explicit on/off toggle, active-run gate, and throttle by time (~15–20 s) and distance (~25–50 m); stop on finish/toggle-off/no-run
- [x] 3.2 Push throttled samples to `POST /delivery/me/run/location`; non-blocking on permission denial
- [x] 3.3 Driver `RunMap`: replace the fixed "Tú" constant with the live own-position marker AND draw the driver's own accumulated **trail** (local fixes, Douglas–Peucker for rendering); show stops without a misleading marker when there's no fix yet
- [x] 3.4 A tracking on/off control in the driver view; remove the leftover geolocation constant from Change 1's mock cleanup

## 4. Dispatcher live driver layer (frontend)

- [x] 4.1 Extend the coverage map controller (`components/deliveryroutes/*`, `lib/deliveryRoutes.ts`) to accept driver positions and draw, per active run, a current marker (distinct style, driver-name label) + trail polyline
- [x] 4.2 Staleness: render "hace X min" and de-emphasize markers older than the threshold; remove a run's marker/trail when it finishes (no more events / absent from the read)
- [x] 4.3 Load initial trails from `GET /delivery/positions`, then subscribe to `GET /delivery/positions/events` and apply each **fat** event directly to the driver layer (no refetch); this is separate from the coverage map's existing thin `delivery` doorbell for drops
- [x] 4.4 Wire the layer into `DeliveryRoutesView` (and link it from the dispatch board so the dispatcher can reach it)

## 5. Verify end-to-end

- [x] 5.1 Backend quality gate: ruff, mypy, and delivery test suite pass
- [x] 5.2 Frontend quality gate: type-check, lint, build pass
- [x] 5.3 Drive the flow (Redis up): as a courier, enable tracking during an active run → points append + publish; as the dispatcher, open the coverage map → see the driver marker + trail + staleness update live over SSE; finish the run → marker leaves the layer and the trail is pruned
- [x] 5.4 Verify privacy behavior: no capture without consent, none outside an active run, tracking stops on finish
- [x] 5.5 Update delivery docs / `front/CLAUDE.md` with the location endpoints, the `driver_position` topic, and the tracking behavior
