## ADDED Requirements

### Requirement: Pending summary before closing a session

The system SHALL provide, for an open cash session, a pending summary reporting the session's uncollected orders (count and total with an unpaid remainder) and undelivered deliveries (count of deliveries not in a delivered state).

#### Scenario: Summary reflects unresolved work

- **WHEN** the pending summary is requested for an open session with unpaid orders and deliveries still out
- **THEN** it returns the count and total of uncollected orders and the count of undelivered deliveries for that session

#### Scenario: Clean session

- **WHEN** the pending summary is requested for a session whose orders are all paid and deliveries all delivered
- **THEN** it reports zero uncollected and zero undelivered

### Requirement: Force-close is never blocked by pending items

Closing a cash session SHALL succeed regardless of any pending (uncollected or undelivered) items. The pending summary is advisory only and never prevents a close.

#### Scenario: Close with pending items

- **WHEN** a session with uncollected orders or undelivered deliveries is closed
- **THEN** the close succeeds and the session is marked closed
