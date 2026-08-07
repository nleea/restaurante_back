## ADDED Requirements

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
