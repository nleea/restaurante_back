## Why

Supplier master data shipped (`frontend-purchasing`), but the actual buying loop — purchase
requests, approval, purchase orders, goods receipt, and supplier payments — still has no frontend.
This is the procure-to-pay flow that makes purchasing operational: it lets a branch raise what it
needs, get it approved, order it from a supplier, receive it into stock (the backend writes the
`in`/`purchase` inventory movements), and track what's been paid. It closes the supply side of the
inventory loop that sales already deduct from.

## What Changes

- Extend the **Purchasing service layer** (`purchasing.api.ts`) with the flow endpoints over
  `/purchasing`: requests (`POST /requests`, `GET /requests?status_filter=`,
  `GET /requests/{id}/items`, `POST /requests/{id}/approve`, `POST /requests/{id}/reject`); orders
  (`POST /orders`, `GET /orders?status_filter=`, `GET /orders/{id}/items`,
  `POST /orders/{id}/receive`); and payments (`POST /orders/{id}/payments`,
  `GET /orders/{id}/payments`).
- Add a **Procurement store** (`procurement.ts`): the active branch's purchase requests and orders
  (filtered client-side by `branch_id` since the list endpoints filter only by status), the selected
  record's line items, an order's payments, and client-side derivations — a request's line labels,
  an order's outstanding balance (`total − Σ payments`) and received-vs-ordered progress. Reuses the
  suppliers + ingredient directory from the existing purchasing store and the catalog units for
  labels.
- Add the **ProcurementView** screen with two areas, mobile-first master–detail:
  - **Solicitudes** (requests): list by status; create a request (branch + requesting employee +
    reason + line items of ingredient/quantity/unit); **approve**/**reject** a `pending` request
    (gated by `purchasing.approve`, attributed to an employee). Create gated by `purchasing.manage`.
  - **Órdenes** (orders): list by status; create an order from an `approved` request (pick a
    supplier, set each line's ordered quantity and unit price → the order total is the server's
    sum); an order detail showing items with received-vs-ordered progress and payment status, a
    **recibir** action (per-item received quantities → feeds inventory) and a **registrar pago**
    action with the order's outstanding balance. All gated by `purchasing.manage`.
- Add the **route + nav entry** (`/procurement`, permission `purchasing.read`) and a navigation
  link.
- Unit tests for the new service functions and the store (URLs/payloads/status filters, branch
  filtering, write-through refetch, balance and received-progress derivations).

Non-goals: paying a purchase from the POS cash drawer (the backend keeps purchase payments separate
from the cash session); editing or cancelling a posted request/order; partial-line editing after
order creation; costing / weighted-average ingredient cost; multi-branch consolidated reporting; and
realtime/auto-refresh (manual refresh this slice). Supplier and ingredient CRUD remain owned by the
purchasing-suppliers and recipes screens.

## Capabilities

### New Capabilities
- `frontend-purchasing-orders`: the procure-to-pay frontend — create and resolve (approve/reject)
  purchase requests, create purchase orders from approved requests, receive goods into inventory,
  and register supplier payments, scoped to the active branch and gated by `purchasing.read` /
  `purchasing.manage` / `purchasing.approve`, with supplier/ingredient/unit/employee labels resolved
  from the purchasing, recipes, catalog, and staff data.

### Modified Capabilities
<!-- None. Consumes the existing purchasing-management backend unchanged; supplier/ingredient/unit
     data is read-only from the already-built frontend-purchasing, recipes, and catalog. The goods
     receipt's inventory side-effect is backend-owned; this screen does not touch inventory specs. -->

## Impact

- **Frontend code**: extend `front/src/services/purchasing.api.ts`; new
  `front/src/stores/procurement.ts`, `front/src/views/ProcurementView.vue`, and
  `front/src/components/procurement/*`; a route in `front/src/router/index.ts` and a nav link in
  `front/src/components/AppSidebar.vue`. New tests under `front/src/services/__tests__` and
  `front/src/stores/__tests__`.
- **Reuses**: the purchasing store (suppliers + ingredient directory), the catalog store (units),
  the staff store (employee pickers for request/approve/receive/pay), the active-branch context, the
  shared `http` axios instance, `@/lib/money` `formatCOP`, `@/lib/quantity` `formatQuantity`, and the
  `apiError` helpers.
- **Backend**: none — consumes existing `/purchasing` request/order/payment endpoints; goods receipt
  writes inventory movements server-side.
- **Permissions/RBAC**: relies on `purchasing.read` (screen + reads), `purchasing.manage` (create
  request/order, receive, pay) and `purchasing.approve` (approve/reject requests). No new codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
