## 1. Backend — the column

- [x] 1.1 Move `OrderDeliveryModel`, `DeliveryRunModel` and `DeliveryRouteDriverModel` to `BranchScopedMixin` in `delivery/infrastructure/models.py` (the mixin already carries `TenantScopedMixin`, so tenant scoping is unchanged)
- [x] 1.2 Add `branch_id` to the `OrderDelivery`, `DeliveryRun` and `DeliveryRouteDriver` domain entities, keeping the required-then-optional field ordering the module uses
- [x] 1.3 Confirm `migrations/env.py` already sees these model modules (they are pre-existing tables — no new registration expected)

## 2. Backend — the migration

- [x] 2.1 Create `0013_delivery_branch_scoping` with `down_revision = "0012_order_item_notes"` (verify it is still the head first — the chain is `0010 → 0011 → 2ed5e401d539 → 0012`)
- [x] 2.2 Per table, three steps: add `branch_id` nullable → backfill → set `NOT NULL`, then the index and the FK to `branches` (`ondelete=RESTRICT`). Follow `0008_delivery_settings_and_route_map_data` for the `op.execute(sa.text(...))` backfill style
- [x] 2.3 Backfill `order_deliveries.branch_id` from `orders.branch_id` via `order_id`
- [x] 2.4 Backfill `delivery_runs.branch_id` and `delivery_route_drivers.branch_id` from `delivery_routes.branch_id` via `delivery_route_id`
- [x] 2.5 Write `downgrade()` to drop the three columns (the derivation is recomputable from the same FKs, so nothing is lost)

## 3. Backend — derive the branch, never accept it

- [x] 3.1 `create_delivery`: take the branch from the order (`repo.order_branch()` already exists — it was added for geocoding bias)
- [x] 3.2 `create_run` and the attach-route-driver use case: take the branch from the route, which both already load to validate
- [x] 3.3 Confirm no request schema in `delivery/infrastructure/api/schemas.py` gains a `branch_id` — a client must not be able to claim one
- [x] 3.4 Update the repository create methods and the domain ports for the new field

## 4. Backend — scope the reads

- [x] 4.1 `list_deliveries` and `list_runs` (repository + port + use case) take a required branch and filter on it. Remember: the automatic tenancy filter applies `tenant_id` only — the branch filter must be written explicitly
- [x] 4.2 `GET /delivery/deliveries` and `GET /delivery/runs` take `branch_id` as a **required** query param, matching `GET /delivery/routes`
- [x] 4.3 Validate the given branch belongs to the tenant (the module's `_require_branch` guard)

## 5. Backend — close the cross-branch hole

- [x] 5.1 `assign_delivery`: reject with `ConflictError` (409) when the delivery's branch differs from the run's, beside the existing state guards
- [x] 5.2 Confirm the message follows the module's Spanish copy convention

## 6. Backend — tests

- [x] 6.1 Test: a delivery created for a branch-A order carries branch A; a run created for a branch-A route carries branch A — without either request naming a branch
- [x] 6.2 Test: listing deliveries/runs for branch A excludes branch B's records (build two branches — this is the latent bug being fixed, so it must be pinned)
- [x] 6.3 Test: listing without `branch_id` is rejected (422), not silently tenant-wide
- [x] 6.4 Test: assigning a branch-A delivery to a branch-B run is 409 and mutates nothing
- [x] 6.5 Test: same-branch assignment still works (guard against over-rejecting)
- [x] 6.6 Run `poetry run pytest`, `poetry run ruff check .` and `poetry run mypy src` green

## 7. Frontend

- [x] 7.1 `services/delivery.api.ts`: `listDeliveries(branchId, status?)` and `listRuns(branchId, status?)` pass `branch_id`
- [x] 7.2 `stores/dispatch.ts`: `loadDeliveries`/`loadRuns` take a branch and the store remembers it; the ten write-through refetches reuse it; a refetch with no branch is a no-op rather than a tenant-wide fetch (see design §4)
- [x] 7.3 `views/DispatchView.vue`: pass `branch.activeBranchId` to the two loads — it already passes it to routes, settings, staff, orders and tables
- [x] 7.4 `views/DeliveryRoutesView.vue`: pass the branch to its `dispatch.loadDeliveries()` call for the coverage overlay
- [x] 7.5 Update `stores/__tests__/dispatch.spec.ts` and the delivery API specs for the new signatures
- [x] 7.6 Run `pnpm type-check`, `pnpm lint` and `pnpm test:unit` green

## 8. Verify the migration for real

- [x] 8.1 Seed a realistic dataset (`poetry run python -m scripts.seed_demo`) so the backfill has rows to chew on, and record the pre-migration counts of `order_deliveries`, `delivery_runs`, `delivery_route_drivers`
- [x] 8.2 Run `poetry run alembic upgrade head` against the real Postgres. **The test suite cannot catch a broken migration** — `tests/conftest.py` uses SQLite + `Base.metadata.create_all` and never runs Alembic (see design §4 of Context), so this step is the only proof
- [x] 8.3 Assert the backfill: zero NULL `branch_id` in all three tables; every delivery's branch equals its order's; every run's and route driver's equals its route's; row counts unchanged
- [x] 8.4 Assert no pre-existing cross-branch pairing exists (a delivery whose branch differs from its run's) — if one does, the new 409 guard would start rejecting real work
- [x] 8.5 Run `poetry run alembic downgrade -1` then `upgrade head` again to prove the migration is re-runnable
- [x] 8.6 Drive the API: list deliveries/runs for a branch and confirm scoping; confirm a missing `branch_id` is rejected; confirm a cross-branch assign is 409
