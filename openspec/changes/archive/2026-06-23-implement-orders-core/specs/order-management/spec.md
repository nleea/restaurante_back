## ADDED Requirements

### Requirement: Tenant and branch isolation for orders

The system SHALL scope every orders read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate orders or tables of another tenant.

#### Scenario: Tenant cannot see another tenant's orders
- **WHEN** a request for tenant A lists orders
- **THEN** only orders whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches an order id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** an orders endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage dining tables

The system SHALL allow authorized users to create, list, update and deactivate dining tables for a branch. A table's `number` MUST be unique within its branch, and `capacity` MUST be greater than zero.

#### Scenario: Create a table
- **WHEN** an authorized user creates a table with a number unique in the branch and a positive capacity
- **THEN** the table is persisted with status `free` and returned

#### Scenario: Reject duplicate table number in a branch
- **WHEN** a user creates a table whose number already exists in that branch
- **THEN** the system responds with a conflict error

#### Scenario: List tables for a branch
- **WHEN** an authorized user lists tables for a branch of the current tenant
- **THEN** only that branch's tables are returned

### Requirement: Open an order

The system SHALL allow authorized users to open an order on a channel (`dine_in`, `takeaway` or `delivery`) attributed to a serving employee, optionally referencing a dining table and/or a customer. The `branch_id` and `employee_id` MUST belong to the current tenant; a referenced dining table MUST belong to the same branch. An order opens with status `open` and zero totals.

#### Scenario: Open a dine-in order on a table
- **WHEN** an authorized user opens a `dine_in` order with a valid employee and a table in the same branch
- **THEN** the order is created with status `open`, zero subtotal/total
- **AND** the table's status becomes `occupied`

#### Scenario: Open a takeaway order without a table
- **WHEN** an authorized user opens a `takeaway` order with a valid employee and no table
- **THEN** the order is created with status `open`

#### Scenario: Reject unknown employee or table
- **WHEN** a user opens an order whose `employee_id`, `branch_id` or `dining_table_id` does not exist in scope
- **THEN** the system responds 404 Not Found identifying the missing reference

#### Scenario: Reject invalid channel
- **WHEN** a user opens an order with a channel outside the allowed set
- **THEN** the system responds with a validation error

### Requirement: Manage order items

The system SHALL allow authorized users to add, update the quantity of, and remove items on an `open` order. An item references a product variant with an integer `quantity` greater than zero and a unit-price snapshot; its `line_subtotal` SHALL equal `unit_price × quantity` plus the sum of its addon prices. The product variant MUST exist in the tenant.

#### Scenario: Add an item
- **WHEN** an authorized user adds a product variant with quantity 2 and a unit price to an open order
- **THEN** the item is persisted with `line_subtotal` = unit_price × 2
- **AND** the order totals are recomputed

#### Scenario: Reject adding to a non-open order
- **WHEN** a user adds an item to an order that is `closed` or `cancelled`
- **THEN** the system responds with a conflict error

#### Scenario: Reject non-positive quantity
- **WHEN** a user adds or updates an item with quantity zero or negative
- **THEN** the system responds with a validation error

#### Scenario: Remove an item
- **WHEN** an authorized user removes an item from an open order
- **THEN** the item is deleted
- **AND** the order totals are recomputed

### Requirement: Manage item addons

The system SHALL allow authorized users to attach an addon to an order item and detach it, capturing the addon's applied price on the line. The addon MUST exist in the tenant. Attaching or detaching SHALL recompute the item's `line_subtotal` and the order totals.

#### Scenario: Attach an addon
- **WHEN** an authorized user attaches an existing addon to an item on an open order
- **THEN** the addon is recorded with its applied price
- **AND** the item line subtotal and order totals increase accordingly

#### Scenario: Reject unknown addon
- **WHEN** a user attaches an addon that does not exist in the tenant
- **THEN** the system responds 404 Not Found

### Requirement: Order totals and discount

The system SHALL keep an order's `subtotal` equal to the sum of its item line subtotals, and `total` equal to `subtotal − discount`. The system SHALL allow setting an order-level `discount` that MUST be at least zero and at most the current subtotal.

#### Scenario: Totals reflect items
- **WHEN** items are added or removed on an order
- **THEN** the order `subtotal` equals the sum of line subtotals and `total` equals subtotal minus discount

#### Scenario: Apply a valid discount
- **WHEN** an authorized user sets a discount between zero and the subtotal
- **THEN** the order `total` becomes subtotal minus the discount

#### Scenario: Reject a discount above subtotal
- **WHEN** a user sets a discount greater than the subtotal or below zero
- **THEN** the system responds with a validation error

### Requirement: Cancel orders and items

The system SHALL allow authorized users to cancel an `open` order or a single item, recording a cancellation audit entry with a reason, the requesting employee, and whether authorization was required. Cancelling a whole order SHALL set its status to `cancelled` and free any associated table.

#### Scenario: Cancel an item
- **WHEN** an authorized user cancels a single item on an open order with a reason
- **THEN** a cancellation record is created referencing that item
- **AND** the item is marked cancelled and the order totals are recomputed

#### Scenario: Cancel a whole order
- **WHEN** an authorized user cancels an open order with a reason
- **THEN** a cancellation record is created
- **AND** the order status becomes `cancelled` and any associated table becomes `free`

#### Scenario: Reject cancelling a closed order
- **WHEN** a user cancels an order that is already `closed`
- **THEN** the system responds with a conflict error

### Requirement: Close an order

The system SHALL allow authorized users to close an `open` order, stamping `closed_at`, setting status `closed`, and freeing any associated dining table.

#### Scenario: Close an open order
- **WHEN** an authorized user closes an open order
- **THEN** the order status becomes `closed` with `closed_at` set
- **AND** any associated table becomes `free`

#### Scenario: Reject closing a non-open order
- **WHEN** a user closes an order that is already `closed` or `cancelled`
- **THEN** the system responds with a conflict error

### Requirement: Record receipt prints

The system SHALL allow authorized users to record a receipt print for an order, marking whether it is the first print or a reprint, attributed to an employee.

#### Scenario: Record a first print
- **WHEN** an authorized user records a print for an order that has none
- **THEN** a receipt-print record is created with `is_reprint` false

#### Scenario: Record a reprint
- **WHEN** an authorized user records a print for an order that already has one
- **THEN** a receipt-print record is created with `is_reprint` true

### Requirement: RBAC protection of orders endpoints

The system SHALL require `orders.read` for read endpoints, `orders.create` for opening orders and adding items, `orders.update` for modifying open orders (items, addons, discount, close, receipts), and `orders.cancel` for cancellations.

#### Scenario: Read without permission
- **WHEN** a user lacking `orders.read` calls an orders read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Create without permission
- **WHEN** a user lacking `orders.create` tries to open an order
- **THEN** the system responds 403 Forbidden

#### Scenario: Cancel without permission
- **WHEN** a user lacking `orders.cancel` tries to cancel an order or item
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
