# cash-management

## Purpose

Branch-scoped cash-register sessions with an open/close (arqueo) lifecycle and a
movement ledger: open a session with a float, register cash in/out movements
during the shift, and close with reconciliation. The close-time `expected_amount`
reconciles physical cash only (`method = cash`); non-cash methods (card, Nequi,
Daviplata) are recorded but excluded from the drawer count. Tenant/branch-isolated
and RBAC-protected.

Out of scope for this capability: the orders → cash payment integration (an order
payment writing a `cash_movement` of concept `sale`), which is a separate change.
## Requirements
### Requirement: Tenant and branch isolation for cash

The system SHALL scope every cash read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate cash sessions or movements of another tenant.

#### Scenario: Tenant cannot see another tenant's sessions
- **WHEN** a request for tenant A lists cash sessions
- **THEN** only sessions whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a session id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a cash endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Open a cash session

The system SHALL allow authorized users to open a cash session for a branch with a non-negative `opening_amount` and an opening employee. The `branch_id` and `opened_by_employee_id` MUST belong to the current tenant. A branch MUST NOT have more than one `open` session at a time.

#### Scenario: Open a session
- **WHEN** an authorized user opens a session for a branch with no open session and a non-negative opening amount
- **THEN** the session is created with status `open`, `opened_at` set, and returned

#### Scenario: Reject a second open session for the branch
- **WHEN** a user opens a session for a branch that already has an `open` session
- **THEN** the system responds with a conflict error
- **AND** no new session is created

#### Scenario: Reject negative opening amount
- **WHEN** a user opens a session with an opening amount below zero
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown branch or employee
- **WHEN** a user opens a session whose `branch_id` or `opened_by_employee_id` does not exist in the tenant
- **THEN** the system responds 404 Not Found identifying the missing reference

### Requirement: Register cash movements

The system SHALL allow authorized users to register a movement on an `open` session, of type `in` or `out`, with a concept, a positive `amount`, a payment `method`, and an optional loose `reference_id`. Movements on a non-open session SHALL be rejected.

#### Scenario: Register an in movement
- **WHEN** an authorized user registers an `in` movement on an open session with a positive amount
- **THEN** the movement is persisted and returned

#### Scenario: Reject movement on a closed session
- **WHEN** a user registers a movement on a session that is `closed`
- **THEN** the system responds with a conflict error

#### Scenario: Reject non-positive amount
- **WHEN** a user registers a movement with an amount of zero or less
- **THEN** the system responds with a validation error

#### Scenario: List a session's movements
- **WHEN** an authorized user lists movements for a session
- **THEN** only that tenant's movements for that session are returned

### Requirement: View sessions

The system SHALL allow authorized users to retrieve a session, list sessions for a branch (optionally filtered by status), and fetch the current `open` session of a branch.

#### Scenario: Get the current open session
- **WHEN** an authorized user requests the open session of a branch that has one
- **THEN** the system returns that session

#### Scenario: No open session
- **WHEN** an authorized user requests the open session of a branch that has none
- **THEN** the system responds 404 Not Found

### Requirement: Close a cash session with reconciliation

The system SHALL allow authorized users to close an `open` session by submitting a non-negative `counted_amount` (the physically counted cash) and a closing employee. On close the system SHALL compute `expected_amount` as the opening amount plus cash movements in minus cash movements out, set `difference = counted_amount − expected_amount`, stamp `closed_at`, record the closing employee, and set status `closed`.

#### Scenario: Close with reconciliation
- **WHEN** an authorized user closes an open session with a counted amount
- **THEN** the session status becomes `closed` with `closed_at` set
- **AND** `expected_amount` is computed from the opening amount and cash movements
- **AND** `difference` equals counted minus expected

#### Scenario: Reject closing a non-open session
- **WHEN** a user closes a session that is already `closed`
- **THEN** the system responds with a conflict error

#### Scenario: Reject negative counted amount
- **WHEN** a user closes a session with a counted amount below zero
- **THEN** the system responds with a validation error

### Requirement: RBAC protection of cash endpoints

The system SHALL require `cash.read` for read endpoints, `cash.open` to open a session, `cash.close` to close a session, and `cash.move` to register movements.

#### Scenario: Read without permission
- **WHEN** a user lacking `cash.read` calls a cash read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Open without permission
- **WHEN** a user lacking `cash.open` tries to open a session
- **THEN** the system responds 403 Forbidden

#### Scenario: Move without permission
- **WHEN** a user lacking `cash.move` tries to register a movement
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

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

#### Scenario: Uncollected orders alone do not block

- **WHEN** a session with uncollected dine-in orders and no unresolved deliveries is closed
- **THEN** the close succeeds

