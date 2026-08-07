# Give deliveries, runs and route drivers the `branch_id` the model requires

## Why

The delivery module is **half branch-scoped**:

```
DeliveryRouteModel        BranchScoped   ✓
DeliverySettingModel      BranchScoped   ✓
DeliveryRouteDriverModel  TenantScoped   ✗
DeliveryRunModel          TenantScoped   ✗   ← the dispatch run
OrderDeliveryModel        TenantScoped   ✗   ← the delivery itself
OrderModel                BranchScoped   ✓
```

The geography of delivery knows which branch it belongs to; **the operational records do
not**. This is a direct breach of the project's binding rule, which exists precisely to stop
this:

> *"Every business-relevant entity must carry a `branch_id` from the start... This avoids a
> painful migration later. The column is not optional."*

The consequence is live today and invisible only because there is one branch: `list_deliveries`
and `list_runs` filter on `tenant_id` alone, so **the dispatch board of a two-branch tenant
would mix both branches' work into one list**. `DispatchView` already scopes everything else it
loads — routes, settings, staff, orders, tables — by the active branch. Deliveries and runs are
the two calls that don't, because they can't.

It also blocks the next change. Scoping the board to "this cash session" needs the cash
session, and a cash session is **per branch** — so it needs to know which branch a delivery
belongs to. There is no path from a pending delivery to a branch today except through its
order.

The cost only grows: every delivery and run recorded from now on is another row to backfill.

## What Changes

- **`branch_id` on `order_deliveries`, `delivery_runs` and `delivery_route_drivers`**, via
  `BranchScopedMixin`, with an Alembic migration that backfills existing rows. Every row can
  derive its branch deterministically — the source FKs are all `NOT NULL`, so no row can be
  orphaned:

  ```
  order_deliveries.order_id         → orders.branch_id
  delivery_runs.delivery_route_id   → delivery_routes.branch_id
  delivery_route_drivers.route_id   → delivery_routes.branch_id
  ```

- **The branch is derived server-side, never supplied by the client.** A delivery takes its
  branch from its order; a run and a route driver take theirs from the route. No request schema
  gains a `branch_id` field — a client cannot claim a branch it does not own.

- **BREAKING (API): `GET /delivery/deliveries` and `GET /delivery/runs` require `branch_id`.**
  They are tenant-wide today — spec'd as such, and that is the bug. Requiring the parameter
  makes "list every delivery in the tenant" unaskable, and matches `GET /delivery/routes`,
  which has always required it. The only callers are the dispatch board and the coverage map,
  and both already hold an active branch.

- **BREAKING (behaviour): assigning a delivery to a run of another branch is rejected** with a
  409. Possible today and undetectable; the new column is what makes it checkable. This is the
  class of bug that only surfaces when the second branch opens, by which time the data is
  already wrong.

Explicitly **out of scope**:

- **Cash-session scoping, the "sin asignar" default and the history view.** This change is
  their prerequisite, not their delivery.
- **The dispatch store's refetch storm.** Every mutation ends in a full `loadDeliveries()`.
  Branch-scoping shrinks each refetch but the N+1 pattern stays — known debt, tracked
  separately.
- **Branch switching on the board.** The board follows the active branch as it already does.

## Capabilities

### New Capabilities

None. This makes an existing capability obey the project's own data model.

### Modified Capabilities

- `delivery-management`: **Tenant and branch isolation for delivery** — deliveries, runs and
  route drivers carry `branch_id`; it is derived server-side from the order or the route;
  list endpoints scope by it; and a cross-branch assignment is rejected.
- `frontend-delivery-dispatch`: **Dispatch service layer** and **Dispatch store** — the
  deliveries/runs list calls carry the active branch instead of being tenant-wide.

## Impact

**Backend**

- `delivery/infrastructure/models.py` — three models move to `BranchScopedMixin`.
- `migrations/versions/0013_*.py` — new head (down_revision `0012_order_item_notes`). Three
  steps per table: add nullable → backfill from the FK path → set `NOT NULL`. `branch_id` is
  `NOT NULL` with an FK to `branches` (`ondelete=RESTRICT`) and an index.
- `delivery/domain/entities.py` — `OrderDelivery`, `DeliveryRun`, `DeliveryRouteDriver` gain
  the field.
- `delivery/domain/ports.py` + `repositories.py` — list signatures take a branch; creates
  resolve it.
- `delivery/application/use_cases/manage_delivery.py` — derive the branch on create; guard the
  cross-branch assignment.
- `delivery/infrastructure/api/router.py` — `branch_id` becomes a required query param on the
  two list endpoints.
- Note: the automatic tenancy filter (`shared/tenancy/filtering.py`) applies `tenant_id` only.
  `BranchScopedMixin` supplies the column; **branch filtering is explicit in each query** and
  does not come for free with the mixin.

**Frontend**

- `services/delivery.api.ts` — `listDeliveries`/`listRuns` take a branch.
- `stores/dispatch.ts` — must know its branch so the write-through refetches stay scoped.
- `views/DispatchView.vue` (already holds `branch.activeBranchId`) and
  `views/DeliveryRoutesView.vue` (calls `dispatch.loadDeliveries()` for the overlay).

**Risk**

The migration writes to every existing delivery and run. It is deterministic and derived from
`NOT NULL` FKs, so it cannot fail on missing data — but it is not reversible in the sense that
matters: downgrade drops the column and the derivation is lost (recomputable from the same FKs).
