## Why

Comandas (orders) is the operational core — the screen where a shift actually runs. The backend order lifecycle is complete and, with `menu-product-variants` shipped, order items can finally be priced from the client (`unit_price = product active-branch price + variant.extra_price`). One small gap remains: every order operation (`open`, `cancel`, `pay`, `receipt`) requires an `employee_id`, but the typical order-takers (`cashier`, `waiter`) lack `staff.read`, so they cannot resolve their own employee via `GET /staff/employees`. This change adds a tiny "who am I as an employee" endpoint and builds the first comandas slice: take an order from open to close.

## What Changes

- **Backend — resolve the current user's employee** (staff): add `GET /staff/employees/me`, gated by authentication only (a session primitive, like `GET /branches`), returning the current user's employee for the resolved tenant (or `404` if they are not an employee). This lets order-takers obtain their `employee_id` without `staff.read`.
- **Frontend — comandas screen** (first slice: take an order):
  - A `/orders` route + "Comandas" nav entry (gated `orders.read`).
  - **Dining tables**: list the active branch's tables; create a table (gated `orders.create`).
  - **Open an order**: choose channel (`dine_in` / `takeaway` / `delivery`) and, for dine-in, a table; opens against the active branch and the resolved employee.
  - **Order list**: list the branch's open orders (filter by status), open one into its ticket.
  - **Ticket (order detail)**: show items and server-computed totals (subtotal / discount / total); **add an item** (pick a product → its active sellable variant → quantity; `unit_price` computed and sent), **edit quantity**, **remove an item**; **set the order discount**; **close** the order; **cancel** the order (with a reason, using the resolved employee).
- **Deferred to follow-up changes** (explicitly out of scope): payments / cobro (orders→cash, needs an open cash session), receipts/printing, per-item cancellation and addons, authorization-gated cancellations, and the KDS (kitchen) board.

## Capabilities

### New Capabilities
- `frontend-orders`: the Comandas screen — dining tables and the open→items→close order lifecycle for the active branch, scoped by permissions, with client-side price/label resolution.

### Modified Capabilities
- `staff-management`: gains a requirement to resolve the **current user's** employee via `GET /staff/employees/me` (authenticated, no `staff.read`).

## Impact

- **Backend**: one new route `GET /staff/employees/me` (reuses the existing employee read + the identity `get_current_user`); a repository lookup by `user_id`. New integration tests. No migration.
- **Frontend**: `services/orders.api.ts`; `stores/orders.ts` (tables, orders, items, current employee); a `views/OrdersView.vue` + components (tables panel, open-order, ticket/detail with the item picker); a `/orders` route and "Comandas" nav link; reuse of the menu store (products, per-branch prices, variants) and the branch context. Unit tests for the store.
- **Unblocks**: a usable order-taking flow for the pilots; sets up the employee-resolution and price-computation seams that payments and KDS will build on.
