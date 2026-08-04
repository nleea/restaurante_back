## MODIFIED Requirements

### Requirement: Pending summary before closing a session

The system SHALL provide, for an open cash session, a pending summary reporting the session's uncollected orders (count and total with an unpaid remainder) and **unresolved** deliveries (count of deliveries that are in none of the terminal states). The unresolved deliveries in this summary are the ones that block the close; the uncollected orders are advisory.

The summary SHALL derive "terminal" from the single definition owned by the delivery lifecycle,
not from its own copy of the list.

#### Scenario: Summary reflects unresolved work

- **WHEN** the pending summary is requested for an open session with unpaid orders and deliveries still out
- **THEN** it returns the count and total of uncollected orders and the count of unresolved deliveries for that session

#### Scenario: A not-delivered delivery is not counted as unresolved

- **WHEN** the pending summary is requested for a session whose delivery was marked `not_delivered`
- **THEN** that delivery is not counted among the unresolved

#### Scenario: A cancelled delivery is not counted as unresolved

- **WHEN** the pending summary is requested for a session whose delivery was `cancelled` with its order
- **THEN** that delivery is not counted among the unresolved

#### Scenario: Clean session

- **WHEN** the pending summary is requested for a session whose orders are all paid and deliveries all resolved
- **THEN** it reports zero uncollected and zero unresolved

### Requirement: A session cannot close while deliveries are unresolved

Closing a cash session SHALL be refused while any of its deliveries is unresolved. A delivery is
**resolved** when it is in a terminal state — `delivered`, `not_delivered` or `cancelled`; it is
**unresolved** while it is `pending`, `assigned` or `in_transit`. The refusal SHALL identify the
unresolved deliveries so they can be acted on.

There is no override. The way out is to resolve the delivery by saying what happened to it, which
is always possible — any delivery can be marked not delivered from any non-terminal state, and one
whose order was cancelled is released by that cancellation. That records the outcome on the order,
where it belongs, instead of in a note attached to the close.

#### Scenario: Close is refused with a delivery still out

- **WHEN** an authorized user closes a session that has an `in_transit` delivery
- **THEN** the system responds with a conflict error identifying the unresolved deliveries
- **AND** the session remains open

#### Scenario: Close is refused with a delivery that never left

- **WHEN** an authorized user closes a session that has a `pending` or `assigned` delivery
- **THEN** the system responds with a conflict error

#### Scenario: Resolving the last delivery unblocks the close

- **WHEN** the last unresolved delivery of a session is marked delivered or not delivered
- **AND** the session is closed
- **THEN** the close succeeds

#### Scenario: Not delivered counts as resolved

- **WHEN** a session whose only delivery is `not_delivered` is closed
- **THEN** the close succeeds

#### Scenario: A cancelled order stops blocking the till

- **WHEN** the order behind a session's only `pending` delivery is cancelled
- **AND** the session is closed
- **THEN** the close succeeds without anyone having to claim the delivery failed
