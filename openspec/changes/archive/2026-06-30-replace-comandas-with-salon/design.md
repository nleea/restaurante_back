## Context

Two screens overlap. **Salón** (`views/FloorView.vue` + `components/floor/*`) looks like a real
floor plan but runs on a seeded prototype store (`stores/floor.ts`): fake tables, a demo menu,
client-side 10% tax, and invented `reserved`/`seatedAt`/`section` fields. **Comandas**
(`views/OrdersView.vue` + `components/orders/OrdersPanel.vue`) is the working screen: it uses the
`orders` store, which is a complete write-through layer over `services/orders.api.ts` (tables,
orders, variant-priced items, payments, discount, close/cancel, employee resolution, and a
menu-derived variant index).

The backend contract (from `services/orders.api.ts`) is the binding constraint:
- `DiningTable` = `{ id, branch_id, number, capacity, status, is_active }`. `status` is **binary**:
  `'free'` or occupied. There is **no** reservation, section, or seating timestamp.
- `Order` = `{ id, branch_id, channel, employee_id, status, subtotal, discount, total,
  dining_table_id, customer_id, ... , closed_at }`. Amounts are **decimal strings**, totals are
  **server-computed**. There is **no** `opened_at`/tax field, and **no** transfer endpoint.
- Items are `product_variant_id` + quantity; `unit_price = branch price + variant.extra_price`.
- Occupancy is implicit: a table is occupied iff it currently backs an open order.

## Goals / Non-Goals

**Goals:**
- One operational floor screen (Salón) backed entirely by the real backend, replacing Comandas.
- Preserve every capability Comandas had: open/list orders, edit the ticket, payments, discount,
  close, cancel, register tables, employee resolution, branch scoping.
- Keep the "El Pase" Salón visual identity (docket cards, seat chairs, semantic status colors).
- Reuse `orders` store, `menu`/`branch` stores, and `OrderTicket` verbatim — no reimplementation of
  the order lifecycle.

**Non-Goals:**
- No backend changes. Reservations, seating time, table sections, and table transfer stay out.
- No new delivery tracking in Salón — the Delivery/Dispatch modules keep that; Salón only *creates*
  a delivery-channel order.
- No change to payments/settlement behavior (reached through the ticket, unchanged).

## Decisions

- **Delete `stores/floor.ts`; Salón consumes the `orders` store.** The prototype store duplicates
  what `orders` already does correctly (write-through, server totals). Rather than teach the fake
  store to call APIs, delete it and bind the view to `orders` + `branch` + `menu`. *Alternative:*
  keep `floor.ts` as an adapter over `orders` — rejected as a redundant indirection layer.
- **Derive table state from orders, not a table field.** Build a per-table view-model:
  `occupied = orders.orders.find(o => o.dining_table_id === table.id && o.status is open)`. The card
  reads that order's `total`. This matches the backend's implicit occupancy and needs no new state.
- **Reuse `OrderTicket` for the detail.** The action panel's "view/edit/pay/close/cancel" opens the
  existing ticket component (already handling variants, payments, discount, close, cancel with the
  right permission gating and the 409-no-cash-session message). Salón contributes only the floor
  grid, the per-table panel, register-table, and delivery-open. *Alternative:* the prototype
  `OrderBuilder` — rejected: it uses a demo menu, integer cents, and client 10% tax that contradict
  the backend model.
- **Cut prototype-only features explicitly.** `reserved` + reservation time, the `section`
  dropdown, `transfer` table, and the `dwell`/`heat` glow are removed because the backend exposes no
  reservation, section, transfer, or seating timestamp. The docket visual identity (mono number,
  seat chairs, free/occupied color) is retained on real data. If the floor later needs turnover
  pressure, the backend must expose `opened_at` (then heat can be revived from real order age).
- **Register-table drops `section`.** `POST /orders/tables` takes only `branch_id, number, capacity`.
  The modal keeps the editable auto-incremented number + capacity, and the section field is removed.
- **`/orders` → redirect to `/floor`.** A router redirect preserves any deep links/bookmarks; the
  route, view, panel, and nav entry are otherwise deleted.

## Risks / Trade-offs

- **Losing the heat/reservation "signature"** → The one bold visual moment depended on data that
  doesn't exist server-side. Mitigation: keep the docket/seat/color identity (still distinctive on
  real data); document heat as a backend-gated follow-up rather than fake it.
- **Feature-parity regressions when deleting Comandas** → A capability (e.g. takeaway orders, order
  cancel reason) could be dropped silently. Mitigation: the `frontend-salon` spec enumerates the
  retained flows; tasks include a parity checklist against the removed `OrdersPanel`.
- **`orders` store tests must stay green** → The store is reused unchanged; only the view layer
  changes. Mitigation: do not touch `stores/orders.ts`; delete only `stores/floor.ts` + its spec and
  add new view-model/mapping tests.
- **Takeaway channel has no floor home** → Comandas could open `takeaway` orders; the floor is
  table-centric. Mitigation: keep takeaway reachable via the same "new order" affordance (channel
  select) or fold it into the delivery/quick-order action; called out as an open question.

## Migration Plan

1. Rewrite `FloorView` + `floor/*` components against `orders`/`branch`/`menu`; embed `OrderTicket`.
2. Add `/floor` redirect from `/orders`; remove `/orders` route, `OrdersView`, `OrdersPanel`, and the
   "Comandas" nav entry (keep only "Salón").
3. Delete `stores/floor.ts` and `stores/__tests__/floor.spec.ts`; add tests for the new table
   view-model (occupancy derivation, total mapping) and any pure mapping helpers.
4. Run `type-check`, `vitest`, `lint`; verify parity against the removed panel.

Rollback: revert the change set; `orders` store and `OrderTicket` are untouched, so Comandas returns
intact.

## Open Questions (resolved)

- **Takeaway / no-table orders** → RESOLVED: a single **"Nueva orden"** action opens a dialog with a
  channel select (Mesa / Para llevar / Domicilio); for `dine_in` it also picks a free table. This
  keeps full parity with Comandas' channel support in one affordance. (Register-table stays its own
  button.)
- **Customer on delivery open** → RESOLVED: **no customer selection.** `openOrder` accepts only
  `{ branch_id, channel, employee_id, dining_table_id }` — there is no `customer_id` parameter, so
  linking a customer at open time would require a backend change (out of scope). Customer/address
  linking stays in the Delivery module.
