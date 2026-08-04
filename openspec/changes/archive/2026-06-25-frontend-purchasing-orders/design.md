## Context

`frontend-purchasing` shipped supplier master data; this change builds the rest of the
`/purchasing` flow. The contract (tenant resolved by subdomain; list endpoints filter only by
`status_filter`, responses carry `branch_id`):

- **Requests** (`purchasing.read` read / `purchasing.manage` create / `purchasing.approve` resolve):
  `POST /purchasing/requests` (`{ branch_id, requested_by_employee_id, reason?, items[] }`, item =
  `{ ingredient_id, requested_quantity, unit_of_measure_id }`), `GET /purchasing/requests?status_filter=`,
  `GET /purchasing/requests/{id}/items`, `POST /purchasing/requests/{id}/approve` and `/reject`
  (`{ employee_id }`). `PurchaseRequest = { id, branch_id, requested_by_employee_id, status:
  pending|approved|rejected, reason, approved_by_employee_id, resolved_at }`.
- **Orders** (`purchasing.read` / `purchasing.manage`): `POST /purchasing/orders`
  (`{ purchase_request_id, supplier_id, items[] }`, item = `{ ingredient_id, ordered_quantity,
  unit_price, unit_of_measure_id }`), `GET /purchasing/orders?status_filter=`,
  `GET /purchasing/orders/{id}/items`, `POST /purchasing/orders/{id}/receive`
  (`{ received_by_employee_id, items[] }`, item = `{ order_item_id, quantity }`). `PurchaseOrder =
  { id, branch_id, purchase_request_id, supplier_id, status: created|partially_received|received,
  payment_status: pending|partial|paid, total }`; `OrderItem = { id, purchase_order_id,
  ingredient_id, ordered_quantity, received_quantity, unit_price, unit_of_measure_id }`.
- **Payments** (`purchasing.read` / `purchasing.manage`): `POST /purchasing/orders/{id}/payments`
  (`{ amount, method, employee_id }`), `GET /purchasing/orders/{id}/payments`. `PurchasePayment =
  { id, purchase_order_id, amount, method, employee_id }`.
- All money/quantity fields are server-side `Decimal`, serialized as **strings**.

Four facts drive the design: (1) the **list endpoints are status-only**, so branch scoping is done
client-side by filtering on the `branch_id` each record carries; (2) records are **id-only**, so
labels (ingredient/unit/supplier/employee) are resolved from already-built stores — the purchasing
store (suppliers + ingredient index), the catalog units, and the staff employees; (3) the flow mixes
**money** (`unit_price`, `total`, `amount`) and **physical quantity** (`*_quantity`), so it uses both
`formatCOP` and `formatQuantity`; and (4) the flow is a **state machine** — a request goes
pending→approved/rejected, an order created→partially_received→received with an independent
payment_status pending→partial→paid — so the UI offers each action only in the state that allows it.
Conventions follow the existing screens (Vue 3 `<script setup>`, Pinia options stores, PrimeVue +
Tailwind, the shared `@/lib/http` axios instance, active-branch scope, mobile-first master–detail).

## Goals / Non-Goals

**Goals:**
- A working buying loop: raise a request → approve → order from a supplier → receive into stock →
  pay, all branch-scoped and state-aware.
- Reuse the supplier/ingredient/unit/employee data already loaded by other stores for labels rather
  than new directories.
- Mirror the established store discipline (write-through, `can()` gating) and master–detail UX.

**Non-Goals:**
- Paying a purchase from the POS cash drawer (backend keeps these separate); editing/cancelling a
  posted request or order; line edits after order creation; costing/weighted-average cost;
  consolidated multi-branch reporting; realtime/auto-refresh.

## Decisions

**1. One `ProcurementView` with two areas (Solicitudes / Órdenes), each master–detail.** The two
stages share a screen via the house tabbed pattern; requests is the default. Order detail (items +
receipt + payments) lives in the Órdenes area. Rejected: separate screens — the request→order
hand-off reads better in one place, and both are "purchasing.read" gated.

**2. Branch scoping is client-side.** Because the list endpoints take only `status_filter`, the store
fetches by status (or all) and filters to `branch.activeBranchId` using each record's `branch_id`.
Create payloads send the active branch's id. Noted as a backend gap (a `branch_id` query would be
cleaner) but non-blocking at pilot volume. Re-scoping on branch change clears the selection and
reloads.

**3. A dedicated `procurement` store, separate from the suppliers `purchasing` store.** Suppliers are
tenant master data; requests/orders are branch-scoped transactions with their own lifecycle, so they
get their own store to keep each focused. The procurement store *reads* the purchasing store
(`ingredientLabel`, `unitAbbrOf`, supplier names) and the staff store (employee names) for labels —
it does not duplicate those directories. It ensures they're loaded on open.

**4. Money vs quantity are formatted distinctly.** `unit_price`, `total`, and payment `amount` use
`formatCOP` and the currency InputNumber; `requested/ordered/received` quantities use
`formatQuantity` with the ingredient's unit. The order total is always the server's; the only client
arithmetic is the **outstanding balance** (`total − Σ payments`) computed in integer cents (as the
cash screen does) and labelled guidance — `payment_status` stays authoritative.

**5. Actions are state-gated.** Approve/reject show only for `pending` requests; "create order" shows
only for `approved` requests not yet ordered; receive shows while an order is not fully `received`;
pay shows while `payment_status !== 'paid'`. Each control is additionally permission-gated
(`purchasing.approve` for resolve, `purchasing.manage` for create/receive/pay).

**6. Store shape.** State: `requests: PurchaseRequest[]`, `requestItems: Record<id, Item[]>`,
`orders: PurchaseOrder[]`, `orderItems: Record<id, Item[]>`, `payments: Record<orderId, Payment[]>`,
`selectedRequestId`, `selectedOrderId`. Getters: `branchRequests`/`branchOrders` (active-branch
filter), `outstandingBalance(orderId)`, `receiptProgress(item)`. Actions (write-through):
`loadRequests(status?)`, `loadOrders(status?)`, `loadRequestItems(id)`, `loadOrderItems(id)`,
`loadPayments(orderId)`, `createRequest`, `approveRequest`, `rejectRequest`, `createOrder`,
`receiveOrder`, `registerPayment` — each refetching the affected collection.

## Risks / Trade-offs

- **Client-side branch filtering** → if a tenant has many branches' requests, the client fetches all
  and filters. → Mitigation: status filter trims the set; pilot volume is small; a backend
  `branch_id` filter is a clean future add. Logged, not silently assumed complete.
- **Label resolution is best-effort** → an id without a loaded label shows a short ref. → Mitigation:
  ensure suppliers/ingredients/units/employees are loaded when the screen opens; degrade clearly.
- **Order creation pre-fills from request items** → quantities default to the requested amounts but
  unit prices start from the supplier's reference price when available, else blank → Mitigation: the
  form lets the buyer adjust every line before submit; total is recomputed by the server.
- **Receipt over-receiving / payment over the total** → backend validates; the UI caps inputs to the
  remaining quantity / balance where known and surfaces 409/422 as friendly messages.
- **Mixed money/quantity decimals** → a wrong formatter would mislead → Mitigation: prices via
  `formatCOP`, quantities via `formatQuantity` with the unit, never crossed.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`purchasing.read` / `purchasing.manage` / `purchasing.approve` permissions. Rollback = revert the new
files, the service additions, the router entry, and the nav link; no persisted client state.

## Open Questions

- Should requests/orders lists gain a backend `branch_id` filter? Deferred — client filtering is fine
  at pilot scale; flagged for when volume grows.
- Should order creation auto-pull the supplier's catalog reference price per line? Planned as a
  convenience pre-fill (the supplier-ingredient `reference_price` exists); non-blocking, noted in
  tasks.
