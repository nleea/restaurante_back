## MODIFIED Requirements

### Requirement: Route an order to the kitchen

The system SHALL allow authorized users to route an order to the kitchen: for each non-cancelled order item, the system resolves the item's product (via its product variant) and creates a ticket (`order_item_stations`) in state `pending` for each station configured for that product, at the order's branch. An item whose product has no configured station SHALL NOT be routed silently: routing SHALL surface it so that an order the kitchen cannot see is never reported as sent. Routing SHALL be idempotent — an item already routed to a station SHALL NOT be duplicated — and this uniqueness SHALL be enforced by a database unique constraint on `(order_item_id, kitchen_station_id)` so concurrent routes converge instead of duplicating.

A station-less item should be unreachable, because a variant cannot be sold without one. This is the second net, for the orders taken before that rule existed and for any path that activates a variant without passing through it. Returning success with zero tickets is what let a paid order be closed while nobody cooked it.

Routing an order whose payment method is anything other than cash SHALL be refused while its payment is unverified, so the kitchen never cooks a prepaid order whose money has not been confirmed. Cash orders SHALL route with no payment precondition — their money arrives at the door.

#### Scenario: Route creates tickets per configured station
- **WHEN** an authorized user routes an order whose item's product is mapped to a station
- **THEN** a `pending` ticket is created for that item at that station

#### Scenario: An item without a configured station is never reported as sent
- **WHEN** an order item's product has no station mapping
- **THEN** routing does not report that item as sent to the kitchen, and identifies it so someone
  can act on it

#### Scenario: Cancelled items are not routed
- **WHEN** an order with a cancelled item is routed
- **THEN** no ticket is created for the cancelled item

#### Scenario: Routing is idempotent
- **WHEN** an order is routed twice
- **THEN** no duplicate tickets are created for an item-station already routed

#### Scenario: An unverified prepaid order is not routed
- **WHEN** a user routes an order whose payment method is not cash and whose payment is unverified
- **THEN** the system refuses and no ticket is created

#### Scenario: A cash order routes with no payment check
- **WHEN** a user routes an unpaid cash order
- **THEN** its tickets are created

## ADDED Requirements

### Requirement: The business can see which products cannot be sold yet

The system SHALL report the products that have no kitchen station mapped, so the gap is found
before a customer pays for one of them.

This exists because the gap is invisible by nature: a product without a station looks exactly like
any other on the menu, and only stops existing at the moment the kitchen should have received it.

#### Scenario: List the products with no station
- **WHEN** an authorized user asks which products have no kitchen station
- **THEN** the system returns them, including the ones whose variants are currently active
