## ADDED Requirements

### Requirement: List closed sessions for a branch

The system SHALL provide a read that lists a branch's closed cash sessions, most recent first, so staff can pick a past shift to review.

#### Scenario: Closed sessions listed

- **WHEN** the closed-sessions list is requested for a branch
- **THEN** the branch's closed sessions are returned, most recent first

### Requirement: Per-session operational record

The system SHALL provide, for a given closed session, its operational record — the orders, deliveries, kitchen tickets and payments belonging to that session (`cash_session_id`) — as read-only history alongside the Reporte Z.

#### Scenario: Session record aggregated

- **WHEN** the operational record is requested for a closed session
- **THEN** it returns the orders, deliveries, tickets and payments stamped to that session

#### Scenario: Legacy rows excluded

- **WHEN** a session's record is built
- **THEN** orders/deliveries with no `cash_session_id` are not included
