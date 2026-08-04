## MODIFIED Requirements

### Requirement: Route an order to the kitchen

The system SHALL allow authorized users to route an order to the kitchen: for each non-cancelled order item, the system resolves the item's product (via its product variant) and creates a ticket (`order_item_stations`) in state `pending` for each station configured for that product, at the order's branch. Items whose product has no configured station SHALL produce no ticket. Routing SHALL be idempotent — an item already routed to a station SHALL NOT be duplicated — and this uniqueness SHALL be enforced by a database unique constraint on `(order_item_id, kitchen_station_id)` so concurrent routes converge instead of duplicating.

Routing an order whose payment method is anything other than cash SHALL be refused while its payment is unverified, so the kitchen never cooks a prepaid order whose money has not been confirmed. Cash orders SHALL route with no payment precondition — their money arrives at the door.

#### Scenario: Route creates tickets per configured station
- **WHEN** an authorized user routes an order whose item's product is mapped to a station
- **THEN** a `pending` ticket is created for that item at that station

#### Scenario: Item without a configured station produces no ticket
- **WHEN** an order item's product has no station mapping
- **THEN** routing creates no ticket for that item

#### Scenario: Cancelled items are not routed
- **WHEN** an order with a cancelled item is routed
- **THEN** no ticket is created for the cancelled item

#### Scenario: Routing is idempotent
- **WHEN** an order is routed twice
- **THEN** no duplicate tickets are created for an item-station already routed

#### Scenario: Concurrent routes cannot duplicate a ticket
- **WHEN** two route requests for the same order race each other
- **THEN** at most one ticket exists per (order item, station) afterwards, enforced by the
  database constraint, and both requests complete without error

#### Scenario: An unverified prepaid order is not routed
- **WHEN** a user routes an order whose payment method is `transfer` and whose payments do not cover its total
- **THEN** the system responds with a conflict error and no ticket is created

#### Scenario: A verified prepaid order routes normally
- **WHEN** an order whose payment method is `transfer` has been verified and is routed
- **THEN** its tickets are created as usual

#### Scenario: A cash order routes without payment
- **WHEN** a user routes an unpaid order whose payment method is `cash`
- **THEN** its tickets are created as usual
