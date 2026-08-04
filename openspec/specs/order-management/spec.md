# order-management

## Purpose

Dining tables and the order (comanda) lifecycle — the operational core: open an
order on a channel, add/update/remove items and addons, keep server-computed
totals and an order-level discount, cancel orders or items, close orders, and log
receipt prints. Tenant/branch-isolated and RBAC-protected.

Out of scope for this capability: **payments** (depend on the `cash` module's cash
sessions) and **inventory deduction via recipes** (a separate integration). Full
KDS item-state transitions belong to the `kitchen` capability.
## Requirements
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

The system SHALL allow authorized users to add, update the quantity of, and remove items
on an open order. Each added item MAY carry an optional free-text **kitchen note** (e.g.
"sin lechuga"), set at add time and bounded in length; the note has no price or inventory
effect. Adding an item is still rejected when the variant has no recipe (the inventory
safety-net). Each item read SHALL expose whether it has been **sent to the kitchen**
(`sent` — true once it has at least one kitchen ticket).

#### Scenario: Add an item with a kitchen note

- **WHEN** an authorized user adds an item with a note
- **THEN** the item is created with that note and the note is returned on the item read

#### Scenario: Item is pending until routed

- **WHEN** an item has just been added
- **THEN** its `sent` flag is false and no kitchen ticket exists for it yet

#### Scenario: Item is sent once routed

- **WHEN** the order is routed to the kitchen
- **THEN** the item's `sent` flag is true

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

The system SHALL keep an order's `subtotal` equal to the sum of its item line subtotals and SHALL keep `total` equal to `subtotal − discount + delivery_fee`. `delivery_fee` SHALL be zero for a non-delivery order and for a delivery without a finalized quote; it SHALL be the frozen quoted fee for a quoted delivery and SHALL NOT be derived anew from a currently configured tariff plan. The system SHALL allow setting an order-level `discount` that MUST be at least zero and at most the current subtotal.

#### Scenario: Item totals remain authoritative
- **WHEN** an order's active items sum to a value and it has no delivery fee
- **THEN** its `subtotal` equals the sum of line subtotals and its `total` equals subtotal minus discount

#### Scenario: A quoted delivery contributes to total
- **WHEN** a delivery quote freezes a fee on an order
- **THEN** its `subtotal` remains the sum of items and its `total` becomes subtotal minus discount plus the frozen delivery fee

#### Scenario: Apply a valid discount
- **WHEN** an authorized user sets a discount between zero and the subtotal
- **THEN** the order `total` becomes subtotal minus the discount

#### Scenario: Reject a discount above subtotal
- **WHEN** a user sets a discount greater than the subtotal or below zero
- **THEN** the system rejects the discount without changing the delivery fee or total

### Requirement: Cancel orders and items

The system SHALL allow authorized users to cancel an `open` order or a single item, recording a cancellation audit entry with a reason, the requesting employee, and whether authorization was required. Cancelling a whole order SHALL set its status to `cancelled`, free any associated table, and release its delivery when that delivery never left the store.

Releasing the delivery is the same obligation as freeing the table: the order stops existing, so
everything it was holding has to be let go. A delivery left behind can never reach the kitchen —
its order is gone — and it blocks its shift's cash session with no honest way out.

A delivery that is already `assigned` or `in_transit` SHALL NOT be released by the cancellation.
Someone left with that food, and the outcome belongs to them: it is still resolved by marking it
not delivered, with a reason.

#### Scenario: Cancel an item
- **WHEN** an authorized user cancels a single item on an open order with a reason
- **THEN** a cancellation record is created referencing that item
- **AND** the item is marked cancelled and the order totals are recomputed

#### Scenario: Cancel a whole order
- **WHEN** an authorized user cancels an open order with a reason
- **THEN** a cancellation record is created
- **AND** the order status becomes `cancelled` and any associated table becomes `free`

#### Scenario: Cancelling releases a delivery that never left
- **WHEN** an authorized user cancels an open order whose delivery is still `pending`
- **THEN** that delivery becomes `cancelled` and stops blocking its shift's cash session

#### Scenario: Cancelling does not take a delivery off a courier
- **WHEN** an authorized user cancels an open order whose delivery is `assigned` or `in_transit`
- **THEN** the delivery keeps its status, and its outcome is still recorded by whoever went out with it

#### Scenario: Cancelling a non-delivery order touches no delivery
- **WHEN** an authorized user cancels an open dine-in or takeaway order
- **THEN** the cancellation succeeds and no delivery record is looked for or changed

#### Scenario: Reject cancelling a closed order
- **WHEN** a user cancels an order that is already `closed`
- **THEN** the system responds with a conflict error

### Requirement: Closing an order leaves its delivery alone

Closing an order SHALL NOT release, cancel or otherwise resolve its delivery.

Closing and cancelling are opposites here and confusing them destroys paid work. A closed order
is settled and CARRIES ON — to the kitchen, and from there to dispatch; it is not an order that
ended. Its delivery sits in `pending` waiting to be handed to a courier, which is exactly the
state a release would consume: releasing it would drop a paid order off the dispatch board with
nobody assigned to take it.

A delivery outlives the close of its order and is resolved by whoever takes it out.

#### Scenario: A closed delivery order keeps its delivery
- **WHEN** an order with a `pending` delivery is closed
- **THEN** the delivery keeps its status and remains on the dispatch board, ready to be assigned

#### Scenario: Only cancelling releases the delivery
- **WHEN** the same order is cancelled instead of closed
- **THEN** its `pending` delivery is released

### Requirement: Close an order

The system SHALL allow authorized users to close an `open` order only when it is
settled: the sum of the order's payments MUST be greater than or equal to the
order `total`, UNLESS the order has a registered customer, in which case the
unpaid remainder MAY be closed on credit. On close the system stamps `closed_at`,
sets status `closed`, and frees any associated dining table. Cash overpayment
(payments summing above `total`) is permitted and treated as change. When the
order is underpaid and has no registered customer, the system SHALL reject the
close and leave the order `open`.

#### Scenario: Close a fully paid order
- **WHEN** an authorized user closes an open order whose payments sum to at least its `total`
- **THEN** the order status becomes `closed` with `closed_at` set
- **AND** any associated table becomes `free`

#### Scenario: Overpayment is allowed as change
- **WHEN** an open order's cash payments sum to more than its `total`
- **THEN** the order closes and the excess is treated as change (no error)

#### Scenario: Reject closing an underpaid order with no customer
- **WHEN** a user closes an open order whose payments sum to less than its `total` and which has no registered customer
- **THEN** the system responds with a validation error identifying the missing amount
- **AND** the order remains `open` and no inventory is deducted

#### Scenario: Reject closing a non-open order
- **WHEN** a user closes an order that is already `closed` or `cancelled`
- **THEN** the system responds with a conflict error

### Requirement: Deduct inventory on close via recipes

When an order is closed, the system SHALL deduct ingredients from inventory based on each non-cancelled item's product-variant recipe (BOM). For each recipe line of each item, the system SHALL record an inventory movement of type `out`, reason `sale`, quantity equal to `recipe_line_quantity × item_quantity`, at the order's branch, with `reference_id` equal to the order id, attributed to the order's employee, and decrement the ingredient's on-hand accordingly. Deduction SHALL occur in the same operation as the close.

Deduction SHALL be non-blocking: if an ingredient's on-hand is insufficient, the close still succeeds and the on-hand MAY become negative (signaling a recount is due). A product variant with no recipe SHALL consume nothing. Deduction SHALL be idempotent: an order that has already produced `sale` movements SHALL NOT be deducted again.

#### Scenario: Closing deducts ingredients scaled by quantity
- **WHEN** an order with an item of quantity 3, whose variant recipe uses 150 (g) of an ingredient, is closed
- **THEN** the order status becomes `closed`
- **AND** an inventory `out` movement of reason `sale`, quantity 450, referencing the order, is recorded for that ingredient at the order's branch
- **AND** the ingredient's on-hand decreases by 450

#### Scenario: Insufficient stock still closes and goes negative
- **WHEN** an order is closed and a required ingredient has less on-hand than needed
- **THEN** the close succeeds
- **AND** the ingredient's on-hand becomes negative by the shortfall

#### Scenario: Variant without a recipe consumes nothing
- **WHEN** an order whose item variant has no recipe is closed
- **THEN** the close succeeds
- **AND** no inventory movement is created for that item

#### Scenario: Cancelled items are not deducted
- **WHEN** an order with a cancelled item and an active item is closed
- **THEN** only the active item's recipe ingredients are deducted

#### Scenario: Deduction does not double-count
- **WHEN** an order has already been closed and its ingredients deducted
- **THEN** the order cannot be closed again
- **AND** no additional `sale` movements are produced for that order

### Requirement: Update customer stats on close

When an order with a linked `customer_id` is closed, the system SHALL update that customer's purchase
stats in the same operation as the close: increment `order_count` by one, add the order `total` to
`total_spent`, and set `last_purchase_at` to the close time. An order with no linked customer SHALL
leave all customer stats untouched. The update SHALL occur exactly once per order — because a closed
order cannot be closed again, an order's stats SHALL NOT be counted twice.

#### Scenario: Closing an order updates the linked customer's stats
- **WHEN** an order with a linked customer and a known total is closed
- **THEN** the customer's `order_count` increases by one
- **AND** the order's total is added to the customer's `total_spent`
- **AND** the customer's `last_purchase_at` is set to the close time

#### Scenario: An order without a customer leaves stats untouched
- **WHEN** an order with no `customer_id` is closed
- **THEN** no customer's stats are changed

#### Scenario: Stats are not double-counted
- **WHEN** an order has already been closed and its customer's stats updated
- **THEN** the order cannot be closed again
- **AND** the customer's stats are not incremented a second time

### Requirement: Auto-route new items to the kitchen

Adding an item SHALL NOT route the order to the kitchen. Items are created *pending* and
reach the KDS only when the order is explicitly routed (the "Enviar a cocina" action, via
the kitchen route endpoint). This lets staff compose the full order before the cook
starts, and lets an un-sent order be cancelled with no kitchen impact.

#### Scenario: Adding an item does not create a kitchen ticket

- **WHEN** an authorized user adds an item to an open order
- **THEN** no kitchen ticket is created for it and the order's `kitchen_state` stays `none`

#### Scenario: Explicit routing creates the tickets

- **WHEN** the order is routed to the kitchen after items were added
- **THEN** kitchen tickets are created for the pending items and the order becomes `in_kitchen`

### Requirement: Record receipt prints

The system SHALL allow authorized users to record a receipt print for an order, marking whether it is the first print or a reprint, attributed to an employee.

#### Scenario: Record a first print
- **WHEN** an authorized user records a print for an order that has none
- **THEN** a receipt-print record is created with `is_reprint` false

#### Scenario: Record a reprint
- **WHEN** an authorized user records a print for an order that already has one
- **THEN** a receipt-print record is created with `is_reprint` true

### Requirement: Charge an order against the open cash session

The system SHALL allow authorized users to register a payment for an `open` order with a positive `amount`, a payment `method`, an optional diner reference, and a charging employee that MUST belong to the tenant. The payment MUST be tied to the branch's currently `open` cash session; if the order's branch has no open session, the charge SHALL be rejected. Registering a payment SHALL persist both an order payment record and a cash movement of type `in` and concept `sale` (referencing the order) in that session, atomically.

#### Scenario: Charge an order with an open session
- **WHEN** an authorized user registers a payment for an open order whose branch has an open cash session
- **THEN** an order payment is persisted tied to that session
- **AND** a cash movement of type `in`, concept `sale`, with `reference_id` equal to the order id is persisted in the session

#### Scenario: Cash payment affects the arqueo
- **WHEN** a `cash`-method payment is registered and the session is later closed
- **THEN** the session's `expected_amount` includes that payment

#### Scenario: Non-cash payment is recorded but excluded from the drawer count
- **WHEN** a non-cash payment (e.g. card or Nequi) is registered and the session is later closed
- **THEN** the payment is recorded
- **AND** it does NOT change the session's physical-cash `expected_amount`

#### Scenario: Reject charging without an open session
- **WHEN** a user registers a payment for an order whose branch has no open cash session
- **THEN** the system responds with a conflict error
- **AND** neither an order payment nor a cash movement is created

#### Scenario: Reject charging a non-open order
- **WHEN** a user registers a payment for an order that is `closed` or `cancelled`
- **THEN** the system responds with a conflict error

#### Scenario: Reject non-positive amount
- **WHEN** a user registers a payment with an amount of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown charging employee
- **WHEN** a user registers a payment whose employee does not belong to the tenant
- **THEN** the system responds 404 Not Found

### Requirement: List an order's payments

The system SHALL allow authorized users to list all payments registered for an order, scoped to the current tenant.

#### Scenario: List payments
- **WHEN** an authorized user lists payments for an order
- **THEN** only that tenant's payments for that order are returned

### Requirement: RBAC protection of orders endpoints

The system SHALL require `orders.read` for read endpoints, `orders.create` for opening orders and adding items, `orders.update` for modifying open orders (items, addons, discount, close, receipts), `orders.cancel` for cancellations, and `orders.pay` for charging an order.

#### Scenario: Read without permission
- **WHEN** a user lacking `orders.read` calls an orders read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Create without permission
- **WHEN** a user lacking `orders.create` tries to open an order
- **THEN** the system responds 403 Forbidden

#### Scenario: Cancel without permission
- **WHEN** a user lacking `orders.cancel` tries to cancel an order or item
- **THEN** the system responds 403 Forbidden

#### Scenario: Charge without permission
- **WHEN** a user lacking `orders.pay` tries to register a payment
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

### Requirement: Close an order on customer credit (fiado)

The system SHALL allow closing an underpaid `open` order when it has a registered
customer, recording the unpaid remainder (`total` − sum of payments) as a customer
credit for that customer, with the credit's `reference_id` set to the order and an
initial pending status. The remainder MAY be the full `total` (a fully unpaid
credit sale). No per-customer credit limit is enforced.

#### Scenario: Close with a partial payment and credit the rest
- **WHEN** an authorized user closes an open order for a registered customer whose payments cover part of the `total`
- **THEN** the order closes
- **AND** a customer credit is created for the remainder, referencing the order

#### Scenario: Fully-on-credit close
- **WHEN** an authorized user closes an open order for a registered customer with no payments registered
- **THEN** the order closes and a customer credit equal to the `total` is created for the customer

#### Scenario: Credit is settled through the existing flow
- **WHEN** a customer later pays down a credit created at order close
- **THEN** it is settled through the existing customer credit-payment flow (a cash settlement enters the open cash session)

### Requirement: Close an unpaid order as a write-off

The system SHALL support closing an underpaid order by absorbing the unpaid remainder as a
business loss instead of charging it to the customer. A write-off close SHALL deduct inventory
through recipes exactly like any other close, SHALL mark the order closed, and SHALL NOT create a
customer credit.

This mode SHALL be reachable **only** from resolving an undelivered delivery. It SHALL NOT be
exposed as a general way to close an order: closing without payment is precisely what once made
sales vanish from the register, and the ordinary rule — pay in full or charge it to a registered
customer — SHALL remain in force for every other close.

The loss SHALL be derivable without a dedicated record: a closed order whose delivery is
`not_delivered` and whose payments fall short of its total **is** the write-off.

#### Scenario: An undelivered unpaid order closes without charging the customer

- **WHEN** a delivery of an unpaid cash order for a registered customer is marked not delivered
- **THEN** the order closes
- **AND** no customer credit is created
- **AND** the customer owes nothing for it

#### Scenario: A write-off still deducts what was cooked

- **WHEN** an order is closed as a write-off
- **THEN** its ingredients are deducted through recipes, because the food was prepared

#### Scenario: The write-off is identifiable afterwards

- **WHEN** a closed order whose delivery is `not_delivered` is inspected
- **THEN** the shortfall between its total and its payments is reported as an absorbed loss

#### Scenario: Write-off is not available to ordinary closes

- **WHEN** a user closes an underpaid order from the counter with no undelivered delivery behind it
- **THEN** the existing rules apply unchanged: the close is refused, or the remainder becomes a
  customer credit

#### Scenario: An already-paid undelivered order closes with no shortfall

- **WHEN** a delivery of a fully prepaid order is marked not delivered
- **THEN** the order closes with no remainder to absorb, and its refund is handled separately

### Requirement: Reject order items for variants without a recipe

As a safety net behind the activation guard, the system SHALL reject adding an
order item whose product variant has no recipe items, so a sale can never be
recorded for something that would not deduct inventory. This is normally
unreachable because only variants with a recipe can be activated (sold), but it
guarantees the invariant even if an active variant lost its recipe.

#### Scenario: Reject adding an item for a variant with no recipe
- **WHEN** a user adds an order item whose variant has no recipe items
- **THEN** the system responds with a validation error indicating the product has no recipe
- **AND** no order item is created

#### Scenario: Add an item for a variant that has a recipe
- **WHEN** a user adds an order item whose variant has at least one recipe item
- **THEN** the item is added as today

### Requirement: Assign a customer to an open order

The system SHALL allow an authorized user to assign a registered customer to an
**open** order, so the order can later be closed on credit (fiado). The endpoint SHALL
require the order to exist in the tenant and be `open`, and the customer to exist in the
tenant. Assigning to a closed or cancelled order SHALL be rejected. Reassigning while
the order is still open SHALL be allowed. This is the only way a dine-in order (opened
without a customer) becomes fiado-eligible; the fiado close itself is unchanged.

#### Scenario: Assign a customer to an open order

- **WHEN** an authorized user assigns an existing customer to an open order
- **THEN** the order's `customer_id` is set and the updated order is returned

#### Scenario: Fiado becomes possible after assignment

- **WHEN** a customer has been assigned to an open order that has an unpaid remainder
- **AND** the order is then closed
- **THEN** the order closes and the unpaid remainder is recorded as a credit for that customer

#### Scenario: Reject assignment to a non-open order

- **WHEN** a user assigns a customer to an order that is closed or cancelled
- **THEN** the request is rejected and the order is unchanged

#### Scenario: Reject an unknown customer

- **WHEN** a user assigns a customer id that does not exist in the tenant
- **THEN** the request is rejected with a not-found error

#### Scenario: RBAC and tenancy

- **WHEN** a user without `orders.update` attempts to assign a customer
- **THEN** the request is forbidden
- **AND** the order and customer are always resolved within the caller's tenant only

### Requirement: Order and table changes publish realtime events

Order and dining-table mutations SHALL publish a best-effort `orders` realtime event scoped to the branch, so the open salón/floor refreshes. This SHALL include order created, updated, items changed, closed, and cancelled, and dining-table status changes. Publishing SHALL be best-effort and SHALL NOT fail the mutation if the broker is down.

#### Scenario: An order change notifies the branch
- **WHEN** an order is created, updated, closed, or cancelled on a branch
- **THEN** an `orders` event for that branch is published

#### Scenario: A table status change notifies the branch
- **WHEN** a dining table's status changes
- **THEN** an `orders` event for that branch is published

#### Scenario: A broker outage does not block the mutation
- **WHEN** the broker is unavailable during an order or table mutation
- **THEN** the mutation succeeds and no event is delivered

### Requirement: Orders events stream

The system SHALL expose the branch's `orders` events as an SSE stream under `orders.read`, so the salón can subscribe and refetch on change.

#### Scenario: The floor streams order events
- **WHEN** a client holding `orders.read` opens the orders events stream for a branch
- **THEN** it receives that branch's order and table events

#### Scenario: Streaming without permission is rejected
- **WHEN** a client lacking `orders.read` opens the orders events stream
- **THEN** the request is rejected

### Requirement: Order payment-method intent

The system SHALL support a nullable `payment_method` on an order that records a customer's chosen
payment method as an intent, distinct from an actual `order_payments` record (which represents money
received into a cash session). Setting the intent SHALL NOT register a payment, affect paid totals,
or gate closing.

#### Scenario: Intent is recorded without a payment
- **WHEN** an order is created with a `payment_method` intent
- **THEN** the order stores that method, its paid total remains zero, and no `order_payments` row
  exists until a real payment is registered

#### Scenario: Intent is optional
- **WHEN** an order is created without a `payment_method`
- **THEN** the field is null and order behavior is unchanged

### Requirement: Orders belong to a cash session

Every order SHALL carry the `cash_session_id` of the branch's cash session that was open at the moment it was created. The value is set once at creation and is the single source of truth for which operating shift the order (and its deliveries and kitchen tickets) belongs to.

#### Scenario: Order stamped with the open session

- **WHEN** an order is created for a branch that has an open cash session
- **THEN** the order's `cash_session_id` is set to that open session's id

#### Scenario: Pre-existing orders carry no session

- **WHEN** an order created before this capability existed is read
- **THEN** its `cash_session_id` is null and it is treated as belonging to no live shift

### Requirement: Order creation requires an open cash session

Order creation SHALL be gated at the single creation choke point (`OrderService.open_order`) for every channel (dine-in/salón, storefront, delivery). If the branch has no open cash session, creation SHALL be rejected with a distinct "caja cerrada" error (HTTP 409), not a generic validation error.

#### Scenario: Creation rejected when the caja is closed

- **WHEN** any channel attempts to create an order for a branch with no open cash session
- **THEN** the request is rejected with a distinct closed-caja error (409) and no order is persisted

#### Scenario: Creation succeeds when the caja is open

- **WHEN** a channel creates an order for a branch with an open cash session
- **THEN** the order is created and stamped with that session

### Requirement: Delivery orders can await a quote before payment selection

The system SHALL permit a delivery order to exist with no payment-method intent while its delivery quote is pending. The order SHALL expose that it awaits a quote and SHALL not be represented to a customer as having a final payable total until a delivery fee is finalized.

#### Scenario: New delivery order has no chosen method

- **WHEN** a public customer submits products and a delivery location
- **THEN** the order is created without a payment method and is marked pending quote rather than requiring a provisional payment choice

