# frontend-purchasing-orders

## Purpose

The procure-to-pay frontend — the buyer-facing client for the transactional slice of the backend
`/purchasing` module, building on the supplier master data (`frontend-purchasing`). It runs the
buying loop: raise a purchase request (multi-line: ingredient, quantity, unit), get it approved or
rejected, create a purchase order from an approved request (supplier + per-line ordered quantity and
unit price, the total being the server's sum), receive goods (per item, which feeds inventory via
the backend's `in`/`purchase` movements), and register supplier payments. The screen is scoped to
the active branch; because the list endpoints filter only by status, branch scoping is applied
client-side on each record's `branch_id`. Records are id-only, so labels — ingredient name and unit,
supplier name, employee name — are resolved from the already-loaded purchasing, recipes, catalog,
and staff data, degrading to a short reference when unresolvable. The flow mixes money
(`unit_price`, `total`, payment `amount` → `formatCOP`) and physical quantity (`*_quantity` →
`formatQuantity`), and the only client computation is an order's outstanding balance
(`total − Σ payments`, integer cents) shown as guidance while the server's `status`/`payment_status`
remain authoritative. Actions are both state-gated (approve only on `pending`, receive until
`received`, pay until `paid`) and permission-gated: the screen needs `purchasing.read`,
create/receive/pay need `purchasing.manage`, and approve/reject need `purchasing.approve` — UX
gating only, the backend enforces authorization independently. Paying a purchase from the POS cash
drawer, editing/cancelling posted records, costing, and realtime are out of scope for this slice.
## Requirements
### Requirement: Procurement service layer

The Purchasing API service SHALL expose typed functions covering the procure-to-pay endpoints of
`/purchasing`: requests — create (`POST /requests`), list (`GET /requests`, optional `status_filter`),
list items (`GET /requests/{id}/items`), approve (`POST /requests/{id}/approve`) and reject
(`POST /requests/{id}/reject`); orders — create (`POST /orders`), list (`GET /orders`, optional
`status_filter`), list items (`GET /orders/{id}/items`) and receive (`POST /orders/{id}/receive`);
and payments — register (`POST /orders/{id}/payments`) and list (`GET /orders/{id}/payments`).
Money and quantity fields SHALL be carried as the backend sends them (string-encoded decimals)
without lossy reformatting in transport.

#### Scenario: Create a purchase request with items

- **WHEN** `createRequest({ branch_id, requested_by_employee_id, reason?, items })` is called
- **THEN** it POSTs `/purchasing/requests` and resolves with the created `PurchaseRequest`

#### Scenario: List requests by status

- **WHEN** `listRequests('pending')` is called
- **THEN** it GETs `/purchasing/requests` passing `status_filter=pending` and resolves with the
  array of `PurchaseRequest`

#### Scenario: Approve a request

- **WHEN** `approveRequest(requestId, { employee_id })` is called
- **THEN** it POSTs `/purchasing/requests/{requestId}/approve` and resolves with the updated
  `PurchaseRequest`

#### Scenario: Create an order from an approved request

- **WHEN** `createOrder({ purchase_request_id, supplier_id, items })` is called
- **THEN** it POSTs `/purchasing/orders` and resolves with the created `PurchaseOrder`

#### Scenario: Receive goods for an order

- **WHEN** `receiveOrder(orderId, { received_by_employee_id, items })` is called
- **THEN** it POSTs `/purchasing/orders/{orderId}/receive` and resolves with the updated
  `PurchaseOrder`

#### Scenario: Register and list payments

- **WHEN** `registerPayment(orderId, { amount, method, employee_id })` is called
- **THEN** it POSTs `/purchasing/orders/{orderId}/payments` and resolves with the created
  `PurchasePayment`; `listPayments(orderId)` GETs `/purchasing/orders/{orderId}/payments`

### Requirement: Procurement store scoped to the active branch

The Procurement store SHALL hold the active branch's purchase requests and orders, the selected
record's line items, and the selected order's payments, filtering the status-only list endpoints to
the active branch by `branch_id`. Mutations (create/approve/reject request, create/receive order,
register payment) SHALL be write-through: after a successful call the store refetches the affected
collection so server state is shown verbatim.

#### Scenario: Lists are scoped to the active branch

- **WHEN** requests or orders are loaded for the active branch
- **THEN** only records whose `branch_id` is the active branch are shown, even though the backend
  list filters only by status

#### Scenario: Approving a request refreshes the list

- **WHEN** a pending request is approved
- **THEN** the store refetches requests so the request shows its `approved` status without a manual
  reload

#### Scenario: Receiving refreshes the order and its items

- **WHEN** goods are received for an order
- **THEN** the store refetches that order and its items so received quantities and the order status
  update

#### Scenario: Registering a payment refreshes the order and payments

- **WHEN** a payment is registered against an order
- **THEN** the store refetches the order and its payments so the payment status and balance update

### Requirement: Outstanding balance and receipt progress derivations

The store SHALL derive client-side, for a selected order, the outstanding balance (`total` minus the
sum of its payments, in integer cents) and each item's received-versus-ordered progress, presenting
the balance as guidance while the server's `payment_status` and `status` remain authoritative.

#### Scenario: Balance reflects payments

- **WHEN** an order with a known total has payments registered
- **THEN** the derived outstanding balance equals the total minus the sum of payments

#### Scenario: Receipt progress reflects received quantity

- **WHEN** an order item has part of its ordered quantity received
- **THEN** the item shows its received-versus-ordered progress

### Requirement: Label resolution for procurement records

The screen SHALL resolve human labels for procurement records — whose requests, orders, and items
carry only ids (ingredient, unit, supplier, employee) — namely the ingredient name and unit, the
supplier name, and the employee name, sourced from the purchasing, recipes, catalog, and staff
data, and SHALL degrade gracefully to a short reference when a label cannot be resolved.

#### Scenario: Resolvable item shows ingredient name and unit

- **WHEN** a line item's `ingredient_id` and unit map to known records
- **THEN** the line shows the ingredient name and unit

#### Scenario: Unresolvable label degrades gracefully

- **WHEN** an id cannot be resolved to a name
- **THEN** a short fallback reference is shown instead of an empty or broken field

### Requirement: Manage purchase requests

The ProcurementView SHALL list the active branch's purchase requests by status and let an authorized
user create a request (requesting employee, optional reason, and one or more line items of
ingredient, positive quantity, and unit); creation SHALL require the `purchasing.manage` permission
and an empty or non-positive-quantity request SHALL be prevented.

#### Scenario: Create a request with line items

- **WHEN** a user with `purchasing.manage` submits a request with at least one valid line item
- **THEN** the request is created with status `pending` and appears in the list

#### Scenario: Empty request is prevented

- **WHEN** a user tries to submit a request with no line items or a non-positive quantity
- **THEN** the form blocks submission

### Requirement: Approve or reject requests

The ProcurementView SHALL let an authorized user approve or reject a `pending` request, attributed to
an employee; these actions SHALL require the `purchasing.approve` permission and SHALL be offered only
for `pending` requests.

#### Scenario: Approve a pending request

- **WHEN** a user with `purchasing.approve` approves a `pending` request
- **THEN** the request becomes `approved` and is eligible to create an order

#### Scenario: Resolve actions hidden for non-pending requests

- **WHEN** a request is already `approved` or `rejected`
- **THEN** no approve or reject action is offered for it

### Requirement: Create purchase orders from approved requests

The ProcurementView SHALL let an authorized user create a purchase order from an `approved` request
by choosing a supplier and setting each line's ordered quantity and unit price; the order total is
the server-computed sum of line amounts. This action SHALL require the `purchasing.manage`
permission.

#### Scenario: Create an order from an approved request

- **WHEN** a user with `purchasing.manage` creates an order from an approved request with a supplier
  and line items
- **THEN** the order is created with status `created` and `payment_status` `pending` and appears in
  the orders list

### Requirement: Receive goods and register payments

The ProcurementView SHALL let an authorized user record received quantities for an order's items
(attributed to an employee), which advances the order to `partially_received` or `received` and feeds
inventory, and register payments against the order (amount, method, employee) showing the outstanding
balance; both actions SHALL require the `purchasing.manage` permission.

#### Scenario: Receive items advances the order

- **WHEN** a user with `purchasing.manage` receives quantities for an order's items
- **THEN** the items' received quantities increase and the order status becomes `partially_received`
  or `received`

#### Scenario: Register a payment updates the balance

- **WHEN** a user with `purchasing.manage` registers a payment against an order
- **THEN** the order's payment status and the outstanding balance update accordingly

### Requirement: Permission gating and navigation

The Compras board SHALL be reachable at `/purchasing` only for authenticated users with
`purchasing.read`, exposed via a single navigation entry; create-request/create-order/receive/pay
controls SHALL require `purchasing.manage`, and approve/reject SHALL require `purchasing.approve`.
The former `/procurement` route SHALL redirect to `/purchasing`. This gating is UX — the backend
enforces authorization independently.

#### Scenario: Read-only Compras user

- **WHEN** the current user has `purchasing.read` but neither `purchasing.manage` nor
  `purchasing.approve`
- **THEN** orders, requests, items, and payments are visible read-only and no create, approve,
  reject, receive, or pay actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `purchasing.read` navigates to `/purchasing`
- **THEN** the router redirects them to the forbidden view

#### Scenario: Legacy procurement route redirects

- **WHEN** a user navigates to `/procurement`
- **THEN** the router redirects them to `/purchasing`

### Requirement: Compras board layout

The Compras screen SHALL be a board whose spine is the branch's purchase orders, with areas
switched by pill tabs — **Órdenes** (the orders table/cards), **Solicitudes** (requests) and
**Proveedores** (supplier management) — and a slide-in detail drawer for the selected order with
**Detalles**, **Ítems** and **Pagos** tabs. Esc and a close control SHALL dismiss the drawer; on
mobile the drawer takes the full width. The board SHALL load orders, requests and payments scoped
to the active branch.

#### Scenario: Open and close the order drawer

- **WHEN** the user clicks a purchase-order row or card
- **THEN** the drawer opens on that order's detail, and Esc or the close control returns to the list

#### Scenario: Switch areas

- **WHEN** the user selects the Solicitudes or Proveedores tab
- **THEN** the board shows that area without leaving the Compras screen

### Requirement: Compras stats and filters

The Órdenes area SHALL show live figures computed from the loaded branch orders — counts of orders
by status (creada, parcialmente recibida, recibida) and the total **por pagar** (sum of outstanding
balances) — and SHALL filter the order list by supplier, order status and a search string (supplier
name or order reference). Active filters SHALL render as dismissable chips with a clear-all control;
filters combine (AND) and apply live.

#### Scenario: Filters combine

- **WHEN** the user picks a supplier, the "parcialmente recibida" status and types a reference fragment
- **THEN** the list shows only orders matching all three and chips for each active filter

#### Scenario: Stats reflect loaded data

- **WHEN** a receipt or a payment changes an order's status or balance
- **THEN** the stat counts and the "por pagar" total update without a page reload

### Requirement: Receipt-progress bar

Every order figure (table rows, cards, and the drawer's header) SHALL render the receipt-progress
bar: a thin bar whose fill maps received-vs-ordered quantity from the `receiptProgress` derivation,
colored by state (creada / warn when partially received / success when fully received).

#### Scenario: Bar reflects partial receipt

- **WHEN** an order has received part but not all of its ordered quantity
- **THEN** its progress bar renders partially filled in the warn color and the row is tinted accordingly

#### Scenario: Bar reflects full receipt

- **WHEN** an order is fully received
- **THEN** its progress bar renders full in the success color

### Requirement: Order detail drawer

The drawer SHALL present the selected order over three tabs: **Detalles** (supplier, status, total,
outstanding balance and progress), **Ítems** (each line's ingredient label, ordered and received
quantities), and **Pagos** (the payment timeline with amounts, methods and the outstanding figure
from `outstandingBalance`). Item and payment labels SHALL resolve through the store's label getters.

#### Scenario: Ítems tab shows received progress per line

- **WHEN** the user opens the Ítems tab of a partially received order
- **THEN** each line shows its ordered and received quantities

#### Scenario: Pagos tab shows the outstanding balance

- **WHEN** the user opens the Pagos tab of an order with payments below its total
- **THEN** the registered payments are listed and the outstanding balance is shown

### Requirement: Receive and pay from the board

The board SHALL let an authorized user receive goods through a **Recibir mercancía** modal (per-item
counted quantities, with the registering employee `Select`) that calls the receive action, and
register a payment through a **Registrar pago** modal (amount, method, employee). Receiving SHALL
require `purchasing.manage`; a receive that exceeds outstanding ordered quantity or a payment without
an open cash session SHALL surface a friendly error and leave the order unchanged.

#### Scenario: Receiving updates progress and stock

- **WHEN** an authorized user receives a quantity for an order's items
- **THEN** the order's received quantities and progress bar update, and the receipt records the
  inventory stock-in already produced by the backend

#### Scenario: Registering a payment reduces the outstanding balance

- **WHEN** an authorized user registers a payment below the order total
- **THEN** the payment appears in the Pagos tab and the outstanding balance decreases

### Requirement: Solicitudes area

The Solicitudes area SHALL list the branch's purchase requests bucketed by status
(pendiente/aprobada/rechazada), let an authorized user create a request, approve or reject a pending
request (gated `purchasing.approve`), and create a purchase order from an approved request. Approve,
reject and order-creation controls SHALL be hidden without the required permission.

#### Scenario: Approve then create an order

- **WHEN** a user with `purchasing.approve` approves a pending request and creates an order from it
- **THEN** the request moves to aprobada and the new order appears in the Órdenes area

#### Scenario: Requests read-only without approve

- **WHEN** the user has `purchasing.read` but not `purchasing.approve`
- **THEN** requests are visible but no approve or reject action is shown

### Requirement: Compras alerts and CSV export

The board SHALL surface an alerts affordance for órdenes con saldo pendiente and órdenes
parcialmente recibidas, each with a quick action (Registrar pago / Recibir), and SHALL export the
current filtered order list to CSV computed client-side.

#### Scenario: Alert quick action

- **WHEN** an order has an outstanding balance
- **THEN** it appears in the alerts area with a Registrar pago quick action

#### Scenario: Export the filtered list

- **WHEN** the user exports while filters are active
- **THEN** the CSV contains only the currently filtered orders

