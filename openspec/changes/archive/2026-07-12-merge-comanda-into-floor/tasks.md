# Tasks — merge Comanda into the Salón

## Backend — assign a customer to an open order (`order-management`)

- [x] 1.1 Use case `assign_customer` — `_require_open_order` guard + `customer_exists`
  check + `update_order({customer_id})`. Added `customer_exists` to repo + ports.
- [x] 1.2 `AssignCustomerRequest` schema; `POST /orders/{order_id}/customer` →
  `OrderResponse`, gated `orders.update` (`_UPDATE`).
- [x] 1.3 Tests (`test_orders_assign_customer.py`): assign → then close unpaid → credit
  recorded for that customer; assign to closed order → 409; unknown customer → 404.
  ruff + mypy clean; full orders suite green (32).

## Frontend — data layer

- [x] 2.1 `orders.api.assignCustomer(orderId, customerId)` → `POST /orders/{id}/customer`.
- [x] 2.2 `orders` store `assignCustomer` action (write-through `refreshOrder`); customers
  store (`activeCustomers`, `customerName`, `loadCustomers`, `selectCustomer`,
  `customerOutstanding`) drives the fiado picker.

## Frontend — routed order detail

- [x] 3.1 Router child `/floor/order/:id` → `OrderDetailView` (`orders.read`); `/comanda`
  redirects to `/floor`.
- [x] 3.2 `OrderDetailView`: resolves the order by `:id`; on deep-link/refresh runs
  `branch.ensureLoaded` + `orders.ensureLoaded` (+ `fetchCategories`); missing/closed/
  cancelled (`status !== 'open'`) → `router.replace('/floor?notice=order-unavailable')`;
  back affordance to the grid.

## Frontend — wire the Comanda components to real stores

- [x] 4.1 `MenuField`/`ProductTile`/`VariantPopover`: real menu products/variants/prices;
  orderable gate (price + active variant); mono tags from category names; tap →
  `orders.addItem`; on-tile variant popover.
- [x] 4.2 `LiveDupe`/`DupeLine`: bound to `orders.itemsOf` + server totals; qty/remove via
  the store; each line "en cocina"; big figure = server `total`; no "Enviar a cocina" —
  primary action opens cobro.
- [x] 4.3 `PaymentSheet` absorbs OrderTicket: split payments, discount, paid/saldo/vuelto,
  close state machine; 409 "no hay caja abierta" + 422 settlement messages preserved.
- [x] 4.4 Fiado picker (search `activeCustomers`, shows chosen customer's outstanding);
  pick → `orders.assignCustomer` → "Fiar y cerrar"; no inline create — "Crear cliente"
  routes to `/customers`.
- [x] 4.5 Cancel-with-reason in the cobro sheet (`cancelOrder`).

## Frontend — Salón navigation + retirement

- [x] 5.1 `FloorView`: "Tomar orden"/"Ver comanda"/no-table clicks + "Nueva orden" now
  `router.push` to `/floor/order/:id`; `OrderTicket` Dialog + ticket plumbing removed;
  a dismissible deep-link notice banner added.
- [x] 5.2 Deleted `OrderTicket.vue`, `lib/comanda.ts`, `ComandaView.vue`; `/comanda`
  redirects; no lingering imports (only a comment mentions the old name).

## Verification

- [x] 6.1 Backend `pytest` green — 3 new assign-customer tests + full suite (262); ruff + mypy.
- [x] 6.2 Frontend green — `type-check`, `lint`, `test:unit` (296), `build` (run independently).
- [ ] 6.3 Live parity walk against the running stack (take order → "en cocina" → qty/discount
  → partial payment → pick customer → Fiar y cerrar → credit appears; full pay → vuelto;
  cancel; deep-link to a closed order redirects). Pending a live run.
