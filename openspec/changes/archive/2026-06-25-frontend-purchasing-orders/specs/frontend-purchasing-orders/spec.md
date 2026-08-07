## ADDED Requirements

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

The Procurement screen SHALL be reachable at `/procurement` only for authenticated users with
`purchasing.read`, exposed via a navigation entry; create-request/create-order/receive/pay controls
SHALL require `purchasing.manage`, and approve/reject SHALL require `purchasing.approve`. This gating
is UX — the backend enforces authorization independently.

#### Scenario: Read-only procurement user

- **WHEN** the current user has `purchasing.read` but neither `purchasing.manage` nor
  `purchasing.approve`
- **THEN** requests, orders, items, and payments are visible read-only and no create, approve,
  reject, receive, or pay actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `purchasing.read` navigates to `/procurement`
- **THEN** the router redirects them to the forbidden view
