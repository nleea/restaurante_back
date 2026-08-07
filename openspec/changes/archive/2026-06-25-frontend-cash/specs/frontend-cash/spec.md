## ADDED Requirements

### Requirement: Cash service layer

The Cash API service SHALL expose typed functions covering the `/cash` endpoints: open a session
(`POST /cash/sessions`); list sessions (`GET /cash/sessions`); get a branch's current open session
(`GET /cash/branches/{branch_id}/open-session`); get a session by id
(`GET /cash/sessions/{session_id}`); close a session (`POST /cash/sessions/{session_id}/close`);
register a movement (`POST /cash/sessions/{session_id}/movements`); and list a session's movements
(`GET /cash/sessions/{session_id}/movements`). Monetary fields SHALL be carried as the backend
sends them (string-encoded decimals) without lossy reformatting in transport.

#### Scenario: Open a session

- **WHEN** `openSession({ branch_id, opened_by_employee_id, opening_amount })` is called
- **THEN** it POSTs to `/cash/sessions` and resolves with the created `CashSession`

#### Scenario: Get the branch's current open session

- **WHEN** `getOpenSession(branchId)` is called
- **THEN** it GETs `/cash/branches/{branchId}/open-session` and resolves with the open `CashSession`

#### Scenario: Register a movement on a session

- **WHEN** `registerMovement(sessionId, { type, concept, amount, method, reference_id? })` is called
- **THEN** it POSTs to `/cash/sessions/{sessionId}/movements` and resolves with the created
  `CashMovement`

#### Scenario: Close a session with a counted amount

- **WHEN** `closeSession(sessionId, { closed_by_employee_id, counted_amount })` is called
- **THEN** it POSTs to `/cash/sessions/{sessionId}/close` and resolves with the closed `CashSession`
  carrying `expected_amount` and `difference`

#### Scenario: List a session's movements

- **WHEN** `listMovements(sessionId)` is called
- **THEN** it GETs `/cash/sessions/{sessionId}/movements` and resolves with the array of
  `CashMovement`

### Requirement: Cash store with branch-scoped session state

The Cash store SHALL hold, for the active branch, the current open session (or its absence), that
session's movements, and a history list of the branch's sessions, and SHALL load the open session
scoped to the active branch. Mutations (open, register movement, close) SHALL be write-through:
after a successful call the store refetches the affected collection so server state is shown
verbatim.

#### Scenario: Load the active branch's open session

- **WHEN** the store loads cash state for the active branch that has an open session
- **THEN** the store holds that open session and its movements, and the screen shows the active
  drawer

#### Scenario: Branch with no open session

- **WHEN** the store loads cash state for a branch that has no open session
- **THEN** the store reflects "no open session" so the screen offers the apertura form rather than a
  drawer

#### Scenario: Registering a movement refreshes the ledger

- **WHEN** a movement is registered on the open session
- **THEN** the store refetches that session's movements so the new entry appears without a manual
  reload

#### Scenario: Closing the session refreshes state

- **WHEN** the open session is closed
- **THEN** the store reflects that the branch no longer has an open session and the closed session
  carries its reconciliation result

### Requirement: Running expected-cash guidance

The store SHALL derive, client-side for the open session, a running expected cash equal to the
opening amount plus `method = cash` movements of type `in` minus `method = cash` movements of type
`out`. Movements with a non-cash method SHALL be excluded from this running figure, mirroring the
backend's drawer reconciliation, and the figure SHALL be presented as pre-close guidance only.

#### Scenario: Cash movements adjust the running expected figure

- **WHEN** a `cash` `in` movement and a `cash` `out` movement exist on the open session
- **THEN** the running expected cash equals opening plus the cash-in minus the cash-out

#### Scenario: Non-cash movements are excluded from the drawer figure

- **WHEN** a movement with a non-`cash` method (e.g. card, Nequi, Daviplata) is registered
- **THEN** it is recorded in the ledger but does not change the running expected cash

### Requirement: Open a cash session

The CashView SHALL, when the active branch has no open session, present an apertura form that
captures an opening employee and a non-negative opening float and opens the session; this action
SHALL require the `cash.open` permission. A surfaced backend conflict (a session already open for
the branch) SHALL be shown as a friendly message rather than a raw error.

#### Scenario: Open the drawer

- **WHEN** a user with `cash.open` submits the apertura form with an employee and a non-negative
  opening amount
- **THEN** the session opens and the screen switches to the active-drawer view

#### Scenario: Apertura blocked when one is already open

- **WHEN** opening is attempted for a branch that already has an open session
- **THEN** the screen shows a friendly "ya hay una caja abierta" message and does not create a
  second session

### Requirement: Register cash movements

The CashView SHALL let an authorized user register an `in` or `out` movement on the open session
with a concept, a positive amount, and a payment method; this action SHALL require the `cash.move`
permission and SHALL be available only while a session is open.

#### Scenario: Register an in movement

- **WHEN** a user with `cash.move` registers an `in` movement with a concept, a positive amount,
  and a method
- **THEN** the movement is added to the ledger and the running expected cash updates per the
  cash-only rule

#### Scenario: Movement controls hidden without an open session

- **WHEN** the branch has no open session
- **THEN** no movement controls are offered and the screen invites opening a session instead

### Requirement: Close a cash session with reconciliation (arqueo)

The CashView SHALL let an authorized user close the open session by entering a closing employee and
a non-negative counted cash amount, then SHALL display the server-computed `expected_amount` and
`difference` (counted minus expected) for the closed session; this action SHALL require the
`cash.close` permission.

#### Scenario: Close with reconciliation

- **WHEN** a user with `cash.close` submits the arqueo with a counted amount
- **THEN** the session closes and the screen shows opening, expected, counted, and the difference

#### Scenario: Difference is shown signed

- **WHEN** a closed session's counted amount differs from the expected amount
- **THEN** the screen presents the difference as a surplus or shortfall, not as a bare unlabeled
  number

### Requirement: Session history with reconciliation detail

The CashView SHALL list the active branch's sessions and let the user select one to view its
detail: opening amount, status, and — for closed sessions — expected, counted, and difference,
together with that session's movements.

#### Scenario: View a past session's reconciliation

- **WHEN** a user selects a closed session from the history
- **THEN** the detail shows its opening, expected, counted, and difference, plus its movement
  ledger

### Requirement: Permission gating and navigation

The Cash screen SHALL be reachable at `/cash` only for authenticated users with `cash.read`,
exposed via a navigation entry; the apertura, movimiento, and arqueo controls SHALL be shown only
with `cash.open`, `cash.move`, and `cash.close` respectively. This gating is UX — the backend
enforces authorization independently.

#### Scenario: Read-only cash user

- **WHEN** the current user has `cash.read` but none of `cash.open` / `cash.move` / `cash.close`
- **THEN** the session and history are visible read-only and no apertura, movimiento, or arqueo
  actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `cash.read` navigates to `/cash`
- **THEN** the router redirects them to the forbidden view
