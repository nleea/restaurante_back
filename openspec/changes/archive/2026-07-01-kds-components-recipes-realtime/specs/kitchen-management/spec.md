# kitchen-management (delta)

## MODIFIED Requirements

### Requirement: Route an order to the kitchen

The system SHALL allow authorized users to route an order to the kitchen: for each non-cancelled order item, the system resolves the item's product (via its product variant) and creates a ticket (`order_item_stations`) in state `pending` for each station configured for that product, at the order's branch. Items whose product has no configured station SHALL produce no ticket. Routing SHALL be idempotent — an item already routed to a station SHALL NOT be duplicated — and this uniqueness SHALL be enforced by a database unique constraint on `(order_item_id, kitchen_station_id)` so concurrent routes converge instead of duplicating.

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

## ADDED Requirements

### Requirement: Kitchen ticket change events

The system SHALL publish a kitchen event when a ticket is created by routing and when a ticket
is advanced, carrying at least the event type, branch id, station id, ticket id and resulting
status, on a channel scoped to the tenant and branch (Redis pub/sub). Publishing SHALL be
best-effort: a publish failure (e.g. Redis unavailable) SHALL NOT fail or delay the underlying
mutation.

#### Scenario: Advancing a ticket publishes an event

- **WHEN** an authorized user advances a ticket
- **THEN** a `ticket_advanced` event with the ticket's station, id and new status is published
  to the tenant/branch channel

#### Scenario: Routing publishes creation events

- **WHEN** routing an order creates tickets
- **THEN** a `ticket_created` event is published for the routed order's tickets on the
  tenant/branch channel

#### Scenario: Publish failure does not break the mutation

- **WHEN** the event broker is unreachable while a ticket is advanced
- **THEN** the advance succeeds and responds normally, and the failure is only logged

### Requirement: Kitchen events stream

The system SHALL expose a server-sent-events endpoint (`GET /kitchen/events`) that streams the
branch's kitchen events to authorized clients (`kitchen.read`), sending a heartbeat comment
periodically so intermediaries keep the connection open, and releasing the subscription when the
client disconnects. Tenancy SHALL be respected: a client only ever receives events of its own
tenant and requested branch.

#### Scenario: Board receives a ticket event

- **WHEN** a client with `kitchen.read` is connected to the events stream for a branch and a
  ticket on that branch is advanced
- **THEN** the client receives the `ticket_advanced` event on the open stream

#### Scenario: Stream is tenant and branch scoped

- **WHEN** a ticket changes in a different tenant or branch than the stream's
- **THEN** the connected client receives nothing for it

#### Scenario: Unauthorized stream is rejected

- **WHEN** a client without `kitchen.read` requests the events stream
- **THEN** the request is rejected with an authorization error
