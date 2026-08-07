## ADDED Requirements

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
