## MODIFIED Requirements

### Requirement: Close an order

The system SHALL allow authorized users to close an `open` order only when it is
settled: the sum of the order's payments MUST be greater than or equal to the
order `total`, UNLESS the order has a registered customer, in which case the
unpaid remainder MAY be closed on credit. On close the system stamps `closed_at`,
sets status `closed`, and frees the associated dining table **only when no other order on that
table is still open**. Cash overpayment (payments summing above `total`) is permitted and treated
as change. When the order is underpaid and has no registered customer, the system SHALL reject the
close and leave the order `open`.

Freeing the table unconditionally was correct while a table could hold one order. It stops being
correct the moment several diners each hold their own order on the same table: the first person to
pay would mark table 5 free with three people still eating at it, and the floor would offer it to
whoever walked in. A table is held by the food on it, not by whoever settles first.

#### Scenario: Close a fully paid order
- **WHEN** an authorized user closes an open order whose payments sum to at least its `total`
- **THEN** the order status becomes `closed` with `closed_at` set

#### Scenario: The last open order frees the table
- **WHEN** the closed order was the only order still open on its table
- **THEN** that table becomes `free`

#### Scenario: A table with diners still eating stays occupied
- **WHEN** an order closes while another order on the same table is still `open`
- **THEN** the table remains `occupied`

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

### Requirement: Cancel orders and items

The system SHALL allow authorized users to cancel an `open` order or a single item, recording a cancellation audit entry with a reason, the requesting employee, and whether authorization was required. Cancelling a whole order SHALL set its status to `cancelled`, free the associated table **only when no other order on that table is still open**, and release its delivery when that delivery never left the store.

Releasing the delivery is the same obligation as freeing the table: the order stops existing, so
everything it was holding has to be let go. A delivery left behind can never reach the kitchen —
its order is gone — and it blocks its shift's cash session with no honest way out.

The table is the exception to "let everything go", and for the same reason as on close: what the
cancelled order was holding may still be held by somebody else's order on the same table.

A delivery that is already `assigned` or `in_transit` SHALL NOT be released by the cancellation.
Someone left with that food, and the outcome belongs to them: it is still resolved by marking it
not delivered, with a reason.

#### Scenario: Cancel an item
- **WHEN** an authorized user cancels a single item on an open order with a reason
- **THEN** a cancellation record is created referencing that item
- **AND** the item is marked cancelled and the order totals are recomputed

#### Scenario: Cancel a whole order
- **WHEN** an authorized user cancels an open order with a reason
- **THEN** a cancellation record is created and the order status becomes `cancelled`

#### Scenario: Cancelling the last open order frees the table
- **WHEN** the cancelled order was the only order still open on its table
- **THEN** that table becomes `free`

#### Scenario: Cancelling one diner's order leaves the table occupied
- **WHEN** an order is cancelled while another order on the same table is still `open`
- **THEN** the table remains `occupied`

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

### Requirement: Manage dining tables

The system SHALL allow authorized users to create, list, update and deactivate dining tables for a branch. A table's `number` MUST be unique within its branch, and `capacity` MUST be greater than zero. Creating a table SHALL also mint its public `code`, unique within the branch and stable across renumbering, and reads SHALL return it.

#### Scenario: Create a table
- **WHEN** an authorized user creates a table with a number unique in the branch and a positive capacity
- **THEN** the table is persisted with status `free` and a generated public `code`, and returned

#### Scenario: Reject duplicate table number in a branch
- **WHEN** a user creates a table whose number already exists in that branch
- **THEN** the system responds with a conflict error

#### Scenario: List tables for a branch
- **WHEN** an authorized user lists tables for a branch of the current tenant
- **THEN** only that branch's tables are returned, each with its public code

## ADDED Requirements

### Requirement: Orders carry their diner and their origin

An order SHALL accept and return `diner_name` (optional) and `origin` (`staff`, `web` or `qr`,
defaulting to `staff`). Both are set at creation and are not editable afterwards: they describe how
the order came into being, and rewriting that later would make the floor and the reports lie about
the past.

#### Scenario: Open an order with a diner name and origin
- **WHEN** an order is opened with a diner name and an origin
- **THEN** both are persisted and returned on subsequent reads

#### Scenario: Defaults hold when neither is given
- **WHEN** an authorized employee opens an order without either field
- **THEN** `diner_name` is null and `origin` is `staff`

#### Scenario: Reject an unknown origin
- **WHEN** an order is opened with an origin outside the allowed set
- **THEN** the system responds with a validation error
