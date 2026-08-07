# frontend-cash

## Purpose

The cash-register (caja / arqueo) frontend — the cashier-facing client for the backend `/cash`
module, scoped to the active branch. It lives on the light office working surface alongside the
other back-office screens. The screen's spine is the branch's single open session: when one
exists it shows the **active drawer** (opening float, the movement ledger, and a live cash-only
"expected cash" estimate) with controls to register in/out movements and to close with
reconciliation (arqueo); when none exists it shows the **apertura** form (opening employee +
float). A **historial** master–detail lists the branch's past sessions and shows each one's
reconciliation (opening / expected / counted / difference, the difference read as a signed
surplus or shortfall) together with its movements. Money travels as string-decimals and is only
reformatted for display via `formatCOP`; the one client-side computation — the running expected
cash — sums `method = cash` movements against the float in integer cents, mirroring the backend's
drawer reconciliation, and is labelled as an estimate because the authoritative `expected_amount`
and `difference` always come from the server at close. The screen is reached with `cash.read`;
the apertura, movimiento, and arqueo controls are gated by `cash.open`, `cash.move`, and
`cash.close` respectively — this gating is UX, the backend enforces authorization independently.
The orders→cash payment integration (an order payment writing a `sale` movement), realtime push,
and editing/voiding posted movements are out of scope for this slice.
## Requirements
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

The Cash station SHALL let an authorized user register a movement on the open session via the
register dialogs — entrada (`in`), retiro (`out`), or gasto (`out`) — each carrying a concept
(≤ 50 chars), a positive amount, a payment method, and a `category`
(`entry` / `withdrawal` / `expense`). This action SHALL require the `cash.move` permission and
SHALL be available only while a session is open. On save, the movement is prepended to the feed
and the running expected cash and shift summary update.

#### Scenario: Register an entrada

- **WHEN** a user with `cash.move` registers an entrada with a concept, a positive amount, and a
  method
- **THEN** the movement is posted with `type = in`, `category = entry`, appears at the top of the
  feed, and the running expected cash updates per the cash-only rule

#### Scenario: Retiro and gasto are distinguishable

- **WHEN** a user registers a retiro and a gasto
- **THEN** both post as `type = out` but with `category = withdrawal` and `category = expense`
  respectively, so the feed and the filter pills can tell them apart

#### Scenario: Movement controls hidden without an open session

- **WHEN** the branch has no open session
- **THEN** no register controls are offered and the screen shows the apertura hero instead

### Requirement: Close a cash session with reconciliation (arqueo)

The Cash station SHALL let an authorized user close the open session through a three-step cierre:
(1) an arqueo denomination counter that sums the counted cash, (2) optional observations and an
incident toggle, and (3) a confirmation showing opening, expected, counted, and the signed
difference. On confirm it SHALL submit the closing employee, the counted amount, and the
observations, then display the server-computed `expected_amount` and `difference`. The
difference SHALL drive a cuadre indicator: exact = calm, small (`< 10.000`) = warm, large
(`≥ 10.000`) = alert. This action SHALL require the `cash.close` permission.

#### Scenario: Close through the three steps

- **WHEN** a user with `cash.close` counts denominations, optionally reports an incident, and
  confirms
- **THEN** the session closes with the counted amount and observations, and the screen shows
  opening, expected, counted, and the signed difference

#### Scenario: Denomination counter drives the counted amount live

- **WHEN** the cashier enters counts per denomination
- **THEN** the total counted and the difference from expected update live, and the cuadre
  indicator reflects the magnitude of the difference

#### Scenario: Difference is shown signed with a cuadre state

- **WHEN** a closed session's counted amount differs from the expected amount
- **THEN** the screen presents the difference as a surplus or shortfall with its cuadre state,
  not as a bare unlabeled number

### Requirement: Session history with reconciliation detail

The CashView SHALL list the active branch's sessions and let the user select one to view its
detail: opening amount, status, and — for closed sessions — expected, counted, and difference,
together with that session's movements.

#### Scenario: View a past session's reconciliation

- **WHEN** a user selects a closed session from the history
- **THEN** the detail shows its opening, expected, counted, and difference, plus its movement
  ledger

### Requirement: Permission gating and navigation

The Cash station SHALL be the `/cash` screen, reachable only for authenticated users with
`cash.read`, exposed via a navigation entry; `/cash/station` SHALL redirect to `/cash`. The
apertura, movimiento, and arqueo controls SHALL be shown only with `cash.open`, `cash.move`, and
`cash.close` respectively. The KPI cockpit and shift summary are reachable with `cash.read`
(the summary endpoint shares that gate) and SHALL degrade to the drawer-only view when the
summary is unavailable. This gating is UX — the backend enforces authorization independently.

#### Scenario: Read-only cash user

- **WHEN** the current user has `cash.read` but none of `cash.open` / `cash.move` / `cash.close`
- **THEN** the station, KPIs, feed, and history are visible read-only and no apertura, movimiento,
  or arqueo actions are shown

#### Scenario: Legacy path redirects

- **WHEN** a user navigates to `/cash/station`
- **THEN** the router redirects them to `/cash`

#### Scenario: Route guarded by permission

- **WHEN** a user without `cash.read` navigates to `/cash`
- **THEN** the router redirects them to the forbidden view

### Requirement: Live shift cockpit

When a session is open, the Cash station SHALL show a KPI strip (sales today, tickets, cash in
drawer, average ticket) and a running shift summary (ingresos/egresos ledger, expected cash,
sales by channel, sales by payment method, tickets) sourced from the cash shift-summary endpoint.
Figures SHALL be mono tabular and animate (count-up) when they change. When the summary endpoint
is unavailable, the station SHALL hide the sales-derived figures (KPIs, channel and method
breakdown) and keep the drawer-truthful figures (expected cash, movement totals) visible.

#### Scenario: Cockpit reflects the open session

- **WHEN** a session is open and the summary loads
- **THEN** the KPI strip and running summary show the session's sales, tickets, breakdowns, and
  expected cash, updating as movements are registered

#### Scenario: Graceful degradation

- **WHEN** the shift-summary endpoint errors or returns nothing
- **THEN** the station renders the drawer-only view (apertura state, movements, expected cash,
  arqueo) without the sales KPIs, rather than showing an error page

### Requirement: Live movement ledger feed

The Cash station SHALL render the open session's movements as a feed ordered by `created_at`
newest-first, each row showing its direction (in = income, out = expense), concept, detail,
author, amount, and time. Filter pills SHALL filter by movement category (todos / ventas /
retiros / gastos / entradas). The feed SHALL refresh by polling while the session is open and
SHALL flash a newly arrived movement (detected by `id`) once. The feed is the manual cash ledger;
automatic sale movements are out of scope until the orders→cash integration lands.

#### Scenario: Newest movement appears first

- **WHEN** a movement is registered
- **THEN** it appears at the top of the feed with its time, and is highlighted briefly

#### Scenario: Filter by category

- **WHEN** the user selects the "Retiros" pill
- **THEN** only movements with `category = withdrawal` are shown

#### Scenario: Polling surfaces external movements

- **WHEN** another client registers a movement on the same open session
- **THEN** the feed surfaces it on the next poll and flashes it once

