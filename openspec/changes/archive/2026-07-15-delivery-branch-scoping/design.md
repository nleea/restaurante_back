## Context

Three delivery tables never got the `branch_id` the project's binding rule requires:
`order_deliveries`, `delivery_runs`, `delivery_route_drivers`. Their siblings
(`delivery_routes`, `delivery_settings`) have it, as does `orders`.

Facts established by reading the code, which shape everything below:

1. **`BranchScopedMixin` gives the column, not the filtering.** The automatic tenancy filter
   (`shared/tenancy/filtering.py`) applies `cls.tenant_id == tenant_id` and nothing else. So
   inheriting the mixin adds `branch_id` (`NOT NULL`, FK → `branches`, `ondelete=RESTRICT`,
   indexed) but every branch filter must be written explicitly in each query.

2. **`NOT NULL` forces a three-step migration** per table: add nullable → backfill → set not
   null.

3. **Every row can derive its branch**, because each source FK is itself `NOT NULL`:

   ```
   order_deliveries.order_id        NOT NULL → orders.branch_id         NOT NULL
   delivery_runs.delivery_route_id  NOT NULL → delivery_routes.branch_id NOT NULL
   delivery_route_drivers.route_id  NOT NULL → delivery_routes.branch_id NOT NULL
   ```

   There is no orphan case to handle. The backfill cannot leave a NULL behind.

4. **The test suite cannot verify the migration.** `tests/conftest.py` points `DATABASE_URL`
   at SQLite and builds the schema with `Base.metadata.create_all` — Alembic never runs. The
   tests will exercise the *models*; the migration itself is only provable against real
   Postgres holding real rows.

5. **A pending delivery has no route.** `delivery_route_id` is set *by* assignment
   (`assign_delivery` copies `run.delivery_route_id`), so an unassigned delivery's only path
   to a branch is through its order. That is why the delivery derives from the order and not
   from the route.

## Goals / Non-Goals

**Goals:**

- The three tables carry `branch_id`, backfilled, `NOT NULL`, obeying the binding rule.
- The dispatch board of a multi-branch tenant cannot see another branch's work.
- The branch is a fact the server derives, never a claim the client makes.
- Close the cross-branch assignment hole that the column makes visible.

**Non-Goals:**

- Cash-session scoping, the unassigned default, the history view (the next change).
- The dispatch store's per-mutation full refetch (known debt).
- Any change to how routes/settings are scoped — they are already correct.
- Branch switching UX on the board.

## Decisions

### 1. Derive the branch server-side; no request schema gains `branch_id`

`create_delivery` reads it from the order (the repository already has `order_branch()`, added
for geocoding bias). `create_run` and `add_route_driver` read it from the route, which both
already load to validate.

Alternative — accept `branch_id` in the request: rejected. It invites a client to claim a
branch that contradicts the order's, creating exactly the inconsistency this change exists to
remove. Derivation makes that unrepresentable.

### 2. `branch_id` is a **required** query param on the two list endpoints

`GET /delivery/deliveries` and `GET /delivery/runs` are tenant-wide today — spec'd as such in
`frontend-delivery-dispatch` ("The deliveries/runs list endpoints are tenant-wide (status
filter only, no branch)"). That sentence *is* the bug.

Required, not optional: an optional param leaves "list the whole tenant" reachable, and it will
be reached. `GET /delivery/routes` has always required `branch_id`, so this makes the module
consistent rather than novel. Both callers (`DispatchView`, `DeliveryRoutesView`) already hold
`branch.activeBranchId`.

### 3. Reject cross-branch assignment with 409

`assign_delivery` gains a check that the delivery's branch equals the run's. It is a
`ConflictError` (409) beside the existing state guards ("el despacho no está en preparación"),
not a validation error — the request is well-formed, the *state* is wrong.

This is only checkable because the column exists. Left alone, the first day of a second branch
starts writing cross-branch rows that nothing detects.

### 4. The dispatch store remembers the branch it loaded

`loadDeliveries`/`loadRuns` gain a branch, but ten write-through actions (`markDelivered`,
`departRun`, `assignDelivery`, …) end in a bare refetch and have no branch to pass. Rather than
thread it through every signature, the store keeps the branch it was last loaded for and the
refetches reuse it; a refetch with no branch set is a no-op rather than a tenant-wide fetch.

Alternative — import `useBranchStore` into the dispatch store (as `stores/staff.ts` and
`stores/procurement.ts` do): viable and precedented, but the dispatch store is currently pure
(it takes what it needs as parameters and imports no other store), and keeping it that way
leaves it testable without a branch fixture.

### 5. Migration shape

One migration, `0013_delivery_branch_scoping`, `down_revision = "0012_order_item_notes"` (the
current head — the chain is `0010 → 0011 → 2ed5e401d539 → 0012`). Per table:

```
add branch_id (nullable)
UPDATE ... SET branch_id = (SELECT ... FROM <parent> WHERE ...)
ALTER ... SET NOT NULL
create index + FK to branches (RESTRICT)
```

`0008_delivery_settings_and_route_map_data` is the precedent for `op.execute(sa.text("UPDATE
…"))` backfills in this repo.

## Risks / Trade-offs

- **The test suite cannot catch a broken migration** (SQLite + `create_all`, no Alembic). A
  green `pytest` says nothing about whether `alembic upgrade head` works. → The migration must
  be run against the real Postgres, with rows present, and the result asserted (no NULLs, every
  delivery's branch equal to its order's, every run's equal to its route's). This is a required
  verification step, not a nicety.

- **Requiring `branch_id` breaks any caller that omits it.** → The only callers are in this
  repo's frontend and both hold an active branch. Any external/manual API caller must add the
  param — hence BREAKING in the proposal.

- **The cross-branch guard could reject work that is currently legal.** If a single-branch
  install somehow holds a delivery and run in different branches, assignment starts failing at
  409. → Impossible for the backfill to produce: the delivery's branch comes from its order and
  the run's from its route, and today's data has one branch. Worth asserting during the
  migration verification anyway.

- **`ondelete=RESTRICT` on `branch_id`** makes a branch undeletable while deliveries reference
  it. → Consistent with `orders` and `delivery_routes`, which already do this. No new
  behaviour.

- **A store that silently no-ops when it has no branch** can look like "the board is empty"
  rather than "the board never loaded". → Both views load the branch before dispatching; the
  no-op is a guard against a refetch racing a branch switch, not a normal path.

## Migration Plan

1. Models → `BranchScopedMixin`; entities, ports, repositories, use cases, router.
2. `alembic revision` → hand-write the three-step upgrade with backfills.
3. **Deploy backend and frontend together.** The list endpoints become required-param, so an
   old frontend against a new backend breaks the board. This is not a rolling-compatible
   change; if that matters, the param must land optional first and be tightened in a follow-up.
4. `alembic upgrade head`, then assert the backfill (see Risks).

**Rollback:** `alembic downgrade -1` drops the three columns; the derivation is recomputable
from the same FKs, so no information is lost. The frontend must be rolled back with it.

## Open Questions

- Should `GET /delivery/routes/{route_id}/drivers` also gain a branch filter? The route already
  pins the branch, so it is redundant — leaving it alone unless the implementation shows
  otherwise.
- `DeliveryRouteDriverModel` is a bridge table (route ↔ employee). Its branch is fully implied
  by the route, so the column is pure denormalisation there. It is included for the rule's sake
  and for symmetry; the alternative (leave it tenant-scoped) would keep the module half-scoped,
  which is the state this change exists to end.
