## MODIFIED Requirements

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

## ADDED Requirements

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
