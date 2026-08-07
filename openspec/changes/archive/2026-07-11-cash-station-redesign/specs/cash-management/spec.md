## ADDED Requirements

### Requirement: Movement timestamps in responses

The system SHALL expose each cash movement's creation timestamp (`created_at`) in the
movement response, so clients can order the ledger and display per-movement times. The
timestamp is already persisted (branch-scoped, timestamped rows); this requirement makes it
part of the API contract.

#### Scenario: A registered movement carries its created_at
- **WHEN** a client registers a movement or lists a session's movements
- **THEN** each returned movement includes a `created_at` timestamp

#### Scenario: Ledger can be ordered by time
- **WHEN** a client lists a session's movements
- **THEN** the movements can be ordered newest-first by `created_at`

### Requirement: Cash movement category

The system SHALL accept an optional `category` on a cash movement, one of
`entry | withdrawal | expense | sale | other`, recorded alongside the movement and returned
in its response. `category` refines the coarse `type` (in/out) so that withdrawals and
expenses (both `out`) are distinguishable; `type` remains the source of truth for the
cash-drawer reconciliation. When omitted, the movement SHALL default to `other` and behave
exactly as before.

#### Scenario: Register a movement with a category
- **WHEN** an authorized user registers an `out` movement with `category = expense`
- **THEN** the movement is persisted with that category and it is returned in the response

#### Scenario: Category is optional and backward compatible
- **WHEN** a movement is registered without a `category`
- **THEN** the movement is accepted and defaults to `other`, and the drawer math is unchanged

#### Scenario: Invalid category is rejected
- **WHEN** a movement is registered with a `category` outside the allowed set
- **THEN** the system responds with a validation error and persists nothing

### Requirement: Cash session close observations

The system SHALL accept optional close observations when closing a session: free-text
`notes`, an `incident` boolean, and an optional `incident_note`. These are persisted on the
session at close and returned in the session response. They do not affect the reconciliation
math (`expected_amount` / `difference` are computed as before).

#### Scenario: Close with observations
- **WHEN** an authorized user closes a session with `notes` and `incident = true` and an
  `incident_note`
- **THEN** the session is closed and the observations are persisted and returned

#### Scenario: Observations are optional
- **WHEN** a session is closed without any observations
- **THEN** the close succeeds and the observation fields are empty/false

### Requirement: Live shift summary for a cash session

The system SHALL expose a shift-summary endpoint for a cash session, gated by `cash.read`,
that returns the session's sales aggregates for its time window and branch: total sales,
ticket count, average ticket, sales broken down by `channel`, sales broken down by payment
`method`, total withdrawals, and the expected cash. The endpoint SHALL compute a valid
summary for an **open** session (window `opened_at` → now), not only for closed sessions,
and SHALL be reachable with only `cash.read` (it does not require `finance.read`).

#### Scenario: Summary of the open session
- **WHEN** an authorized user with `cash.read` requests the summary of an open session
- **THEN** the system returns its sales total, tickets, average ticket, channel and payment
  breakdowns, withdrawals, and expected cash computed over `opened_at`→now

#### Scenario: Summary of a closed session
- **WHEN** an authorized user requests the summary of a closed session
- **THEN** the system returns the aggregates computed over the session's opened→closed window

#### Scenario: Reachable with cash.read only
- **WHEN** a user holding `cash.read` but not `finance.read` requests a session summary
- **THEN** the system returns the summary (does not respond 403)

#### Scenario: Isolation and not-found
- **WHEN** a request asks for the summary of a session that belongs to another tenant
- **THEN** the system responds 404 Not Found
