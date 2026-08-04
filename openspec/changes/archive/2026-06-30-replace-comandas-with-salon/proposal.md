## Why

The front recently gained a "Salón" (floor) view — a visually complete table-management
screen — but it runs on a **local, seeded prototype store** (`stores/floor.ts`) with fake
tables, a demo menu, client-side 10% tax, and invented reservation/heat state. Meanwhile the
real operational screen, **"Comandas"** (`OrdersView` / `OrdersPanel`), already talks to the
backend (`/orders`, `/orders/tables`, items, payments, close/cancel) but presents tables as a
buried collapsible list, not a floor. We have two overlapping screens: one that looks right but
does nothing, and one that works but hides the floor. We want one screen: **Salón, wired to the
real backend**, and Comandas removed.

## What Changes

- Rewire the Salón view onto the real `orders` store (tables, orders, variant-priced items,
  payments, discount, close/cancel) plus the `branch` and `menu` stores. The seeded
  `stores/floor.ts` prototype store is deleted.
- Derive each table's state from the backend: a table is **occupied when it has an open order**,
  **free** otherwise. The docket card shows the open order's server-computed total.
- Table actions become real operations: open a dine-in order on a free table, view/edit the
  ticket (add/remove/adjust variant items with server totals), register payments against the open
  cash session, apply discount, and close or cancel the order.
- "New delivery order" opens a real `channel: 'delivery'` order; detailed driver tracking stays in
  the existing Delivery/Dispatch modules.
- Register-table uses the real `POST /orders/tables` (number + capacity only).
- **BREAKING (UI):** The "Comandas" screen is removed — `OrdersView`, `OrdersPanel`, the
  `/orders` route, and the "Comandas" nav entry. `/orders` redirects to `/floor`. `OrderTicket`
  is kept and reused inside Salón.
- **Cut prototype-only features with no backend support** (documented in design): the *reserved*
  status + reservation time, the *dwell/heat* glow, the table *section* field, *transfer table*,
  and the client-side *10% tax* (the backend models discount, not tax, and does not expose seating
  time, reservations, sections, or a transfer endpoint).

## Capabilities

### New Capabilities
- `frontend-salon`: The Salón floor screen — a live table grid backed by real orders/tables,
  with per-table open/view/pay/close/cancel flows, register-table, and delivery-order creation.

### Modified Capabilities
- `frontend-orders`: The standalone "Comandas" screen is removed — the `/orders` route/nav and the
  open-orders master list. The order lifecycle, employee resolution, table management, ticket, and
  discount/close/cancel behaviors are **unchanged** (same `orders` store, service, and `OrderTicket`)
  and are now hosted by `frontend-salon`, so only the screen-level requirements get a delta.

> Note: `frontend-orders-payments` is **not** modified — payment registration/settlement behavior is
> identical; it is simply reached through Salón's ticket now. No spec delta needed.

## Impact

- **Removed:** `src/views/OrdersView.vue`, `src/components/orders/OrdersPanel.vue`, the `/orders`
  route + "Comandas" sidebar link, `src/stores/floor.ts` and its test.
- **Rewritten:** `src/views/FloorView.vue` and `src/components/floor/*` (TableCard, TablePanel,
  OrderBuilder, RegisterTableModal, DeliveryModal) to consume the real stores.
- **Reused unchanged:** `services/orders.api.ts`, `stores/orders.ts`, `components/orders/OrderTicket.vue`,
  `stores/menu.ts`, `stores/branch.ts`.
- **Routing:** `/orders` → redirect to `/floor`; sidebar "Servicio" group keeps only "Salón".
- **No backend changes.** Reservations, seating timestamps, table sections, and table transfer are
  explicitly out of scope (candidate backend follow-ups if the floor later needs them).
