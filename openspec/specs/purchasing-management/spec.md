# purchasing-management

## Purpose

Procure-to-pay for the supply side of inventory: suppliers and their ingredient
catalog, purchase requests with an approval step, purchase orders, goods receipt
that feeds inventory (`in`/`purchase` movements), and supplier payments. Closes
the inventory loop together with sales (which deduct stock). Tenant/branch-
isolated and RBAC-protected.

Out of scope for this capability: paying a purchase from the POS cash drawer,
costing / weighted-average ingredient cost, and unit conversion between purchase
and stock units (assumed equal).

## Requirements

### Requirement: Tenant and branch isolation for purchasing

The system SHALL scope every purchasing read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate suppliers, requests, orders or payments of another tenant.

#### Scenario: Tenant cannot see another tenant's suppliers
- **WHEN** a request for tenant A lists suppliers
- **THEN** only suppliers whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a purchase order id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a purchasing endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage suppliers

The system SHALL allow authorized users to create, list, retrieve, update and deactivate suppliers (name plus optional tax id, phone, email, address).

#### Scenario: Create a supplier
- **WHEN** an authorized user creates a supplier with a name
- **THEN** the supplier is persisted active and returned

#### Scenario: List and filter suppliers
- **WHEN** an authorized user lists suppliers, optionally by active state
- **THEN** the tenant's matching suppliers are returned

#### Scenario: Deactivate a supplier
- **WHEN** an authorized user deactivates a supplier
- **THEN** the supplier's `is_active` becomes false

### Requirement: Manage supplier ingredients

The system SHALL allow authorized users to register which ingredients a supplier provides, each with a non-negative reference price and a unit of measure, to list a supplier's ingredients, and to remove one. The supplier, ingredient and unit MUST belong to scope; the same supplier-ingredient pair MUST NOT be registered twice.

#### Scenario: Attach an ingredient to a supplier
- **WHEN** an authorized user adds an existing ingredient (with a unit and reference price) to a supplier
- **THEN** the supplier-ingredient is persisted

#### Scenario: Reject duplicate supplier ingredient
- **WHEN** a user adds an ingredient already registered for that supplier
- **THEN** the system responds with a conflict error

#### Scenario: Reject unknown ingredient or unit
- **WHEN** a user adds a supplier ingredient whose ingredient or unit does not exist in scope
- **THEN** the system responds 404 Not Found

### Requirement: Create and resolve purchase requests

The system SHALL allow authorized users to create a purchase request for a branch with one or more line items (ingredient, positive requested quantity, unit), to list and retrieve requests with their items, and to approve or reject a `pending` request (recording the approving employee and resolution time). Approval/rejection requires the `purchasing.approve` permission.

#### Scenario: Create a request with items
- **WHEN** an authorized user creates a request with at least one valid line item
- **THEN** the request is persisted with status `pending` and its items returned

#### Scenario: Reject empty or invalid quantities
- **WHEN** a user creates a request with no items or a non-positive quantity
- **THEN** the system responds with a validation error

#### Scenario: Approve a pending request
- **WHEN** an authorized user with `purchasing.approve` approves a `pending` request
- **THEN** the request status becomes `approved` with the approver and resolution time recorded

#### Scenario: Reject a non-pending request transition
- **WHEN** a user approves or rejects a request that is not `pending`
- **THEN** the system responds with a conflict error

### Requirement: Create purchase orders from approved requests

The system SHALL allow authorized users to create a purchase order from an `approved` purchase request, for a supplier, with line items (ingredient, positive ordered quantity, unit price, unit). The order `total` SHALL be the sum of `ordered_quantity × unit_price` across items. The supplier and request MUST belong to the tenant; the request MUST be `approved`.

#### Scenario: Create an order with computed total
- **WHEN** an authorized user creates an order from an approved request with items
- **THEN** the order is persisted with status `created`, `payment_status` `pending`, and `total` equal to the sum of line amounts

#### Scenario: Reject ordering from a non-approved request
- **WHEN** a user creates an order from a request that is not `approved`
- **THEN** the system responds with a conflict error

### Requirement: Receive goods into inventory

The system SHALL allow authorized users to record received quantities for a purchase order's items. Each receipt SHALL increase the item's `received_quantity`, create an inventory movement of type `in`, reason `purchase`, referencing the order, at the order's branch, attributed to the receiving employee, and increase the ingredient's on-hand. When all items are fully received the order status SHALL become `received`; if some but not all, `partially_received`. Received quantity MUST be positive.

#### Scenario: Receiving increases stock
- **WHEN** an authorized user receives quantity Q for an order item
- **THEN** the item's `received_quantity` increases by Q
- **AND** an inventory `in` movement of reason `purchase`, quantity Q, referencing the order, is recorded for that ingredient at the branch
- **AND** the ingredient's on-hand increases by Q

#### Scenario: Partial receipt sets partially_received
- **WHEN** an order has some but not all ordered quantities received
- **THEN** the order status is `partially_received`

#### Scenario: Full receipt sets received
- **WHEN** every order item's received quantity reaches its ordered quantity
- **THEN** the order status becomes `received`

#### Scenario: Reject non-positive received quantity
- **WHEN** a user receives a quantity of zero or less
- **THEN** the system responds with a validation error

### Requirement: Register purchase payments

The system SHALL allow authorized users to register payments against a purchase order (positive
amount, method, employee) and to list a purchase order's payments. The order `payment_status` SHALL
be `paid` when the sum of payments is at least the order total, `partial` when some but less, and
`pending` when none. When the payment `method` is `cash`, the system SHALL also post a cash movement
of type `out` and concept `purchase_payment` on the open cash session of the purchase order's branch,
referencing the order, written atomically with the payment; if that branch has no open cash session
the cash payment SHALL be rejected with a conflict and neither the payment nor a cash movement SHALL
be persisted. Payments with a non-cash method do not touch any cash session.

#### Scenario: Partial then full payment
- **WHEN** an authorized user registers a payment below the order total
- **THEN** the order `payment_status` becomes `partial`
- **AND** when subsequent payments reach the total it becomes `paid`

#### Scenario: Reject non-positive payment
- **WHEN** a user registers a payment of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Cash payment posts a drawer movement
- **WHEN** a payment with method `cash` is registered against an order whose branch has an open cash
  session
- **THEN** a cash movement of type `out`, concept `purchase_payment`, referencing the order, is
  recorded on that session
- **AND** the session's expected cash decreases by the payment amount

#### Scenario: Cash payment without an open session is rejected
- **WHEN** a payment with method `cash` is registered for an order whose branch has no open cash
  session
- **THEN** the system responds with a conflict error
- **AND** neither the payment nor a cash movement is persisted

#### Scenario: Non-cash payment does not touch the drawer
- **WHEN** a payment with a non-cash method (e.g. card, transfer) is registered
- **THEN** the payment is recorded and no cash movement is created

### Requirement: RBAC protection of purchasing endpoints

The system SHALL require `purchasing.read` for reads, `purchasing.manage` for managing suppliers, supplier ingredients, requests, orders, goods receipt and payments, and `purchasing.approve` for approving or rejecting purchase requests.

#### Scenario: Read without permission
- **WHEN** a user lacking `purchasing.read` calls a purchasing read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Manage without permission
- **WHEN** a user lacking `purchasing.manage` tries to create a supplier or an order
- **THEN** the system responds 403 Forbidden

#### Scenario: Approve without permission
- **WHEN** a user lacking `purchasing.approve` tries to approve a request
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
