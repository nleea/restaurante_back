## MODIFIED Requirements

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

## ADDED Requirements

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
