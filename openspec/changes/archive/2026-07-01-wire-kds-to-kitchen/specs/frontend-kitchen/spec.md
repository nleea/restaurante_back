# frontend-kitchen (delta)

## MODIFIED Requirements

### Requirement: Kitchen store with branch-scoped state

The Kitchen store SHALL hold the active branch's stations, product→station mappings, and the
tickets of **all active stations** (loaded per station and merged), so the board can present the
whole kitchen at once and filter by station client-side. Mutations SHALL be write-through: after
a successful call the store refetches the affected tickets so server state is shown verbatim.

#### Scenario: Load stations for the active branch

- **WHEN** the store loads stations for the active branch
- **THEN** `stations` holds that branch's stations and the board can select one

#### Scenario: Load the whole board

- **WHEN** the store loads tickets for the board
- **THEN** it fetches each active station's tickets and exposes the merged set, keyed so the
  board can group by order and filter by station

#### Scenario: Advancing a ticket refreshes the board

- **WHEN** `advanceTicket` succeeds for a ticket on the board
- **THEN** the store refetches tickets so the ticket reflects its new status without a manual
  reload

#### Scenario: Routing an order refreshes the board

- **WHEN** an open order is routed to the kitchen
- **THEN** the store refetches tickets so newly created tickets appear

### Requirement: Cook-facing ticket board

The KitchenView SHALL present the board as KDS order dockets: each order's tickets grouped into
one docket showing the destination (table number or channel), an order reference, and each dish
with its quantity and its own status rendered as a tappable component row. Advancing a dish SHALL
move its ticket strictly forward (`pending → in_progress → ready`); a `ready` dish SHALL offer no
further action. Each dish row SHALL surface an alert severity derived from its waiting time
(calm → warning → overdue) and dockets SHALL be ordered so the most urgent, oldest work surfaces
first, with fully-ready dockets de-emphasised and sorted last. Dish labels SHALL come from the
store's label resolution, degrading to a short ticket reference when unresolvable.

#### Scenario: Tickets grouped per order into a docket

- **WHEN** the board shows tickets from two different orders
- **THEN** it shows one docket per order, each listing that order's dishes (with quantity),
  destination and reference, and each dish carries its own status and alert severity

#### Scenario: Advance moves a ticket forward

- **WHEN** the cook taps a `pending` dish
- **THEN** its ticket moves to `in_progress`; tapping again moves it to `ready`

#### Scenario: Ready dishes are terminal

- **WHEN** a dish's ticket is `ready`
- **THEN** tapping it performs no mutation and the dish reads as done

#### Scenario: Urgent work surfaces first

- **WHEN** the board shows several dockets
- **THEN** unfinished dockets appear ordered by urgency/age and a docket whose tickets are all
  `ready` sinks below the unfinished ones

### Requirement: Station rail with live backlog

The board SHALL present the branch's active stations as a filter rail driven by the stations in
the database (no hardcoded station set). Each station SHALL show a stable two-letter tag derived
from its name (deterministically uniquified on collision), its name, and a live count of its open
(not-yet-`ready`) tickets. Selecting a station SHALL filter the board to dockets containing that
station's work; a "all stations" selection SHALL show everything.

#### Scenario: Rail reflects DB stations

- **WHEN** the active branch has stations configured in the database
- **THEN** the rail lists exactly those active stations, each with a two-letter tag and name

#### Scenario: Rail shows open counts and filters

- **WHEN** a station has unfinished tickets and the user selects it in the rail
- **THEN** the rail shows that station's open-ticket count and the board filters to dockets with
  work for that station

## ADDED Requirements

### Requirement: Automatic board refresh

The board SHALL refresh its tickets automatically by polling on a fixed cadence (~10 s) while
the board is visible, without user interaction. Polling SHALL skip a tick if the previous fetch
is still in flight, SHALL keep showing the last good data when a poll fails, and SHALL stop when
the board is unmounted. A manual refresh affordance SHALL remain available.

#### Scenario: New tickets appear without interaction

- **WHEN** an order is routed to the kitchen from elsewhere while the board is open
- **THEN** its dockets appear on the board within the polling interval, with no user action

#### Scenario: Failed poll degrades gracefully

- **WHEN** a polling fetch fails
- **THEN** the board keeps the previously loaded tickets and retries on the next tick

### Requirement: Order readiness rollup and bump

The board SHALL derive an order-level readiness state from the order's tickets — an order is
ready when all its tickets are `ready` — and reflect it on the docket. A docket SHALL offer a
bump action (gated by `kitchen.update`) that advances all of the order's remaining tickets to
`ready` using the existing advance endpoint; the action SHALL be disabled while in flight and the
board SHALL show the server's resulting state afterwards.

#### Scenario: Rollup derived from tickets

- **WHEN** the last unfinished ticket of an order reaches `ready`
- **THEN** the docket reads as ready and is de-emphasised per board ordering

#### Scenario: Bump completes an order

- **WHEN** a user with `kitchen.update` bumps a docket with `pending` and `in_progress` tickets
- **THEN** each remaining ticket is advanced to `ready` and the refreshed board shows the order
  fully ready

#### Scenario: Partial bump failure shows server truth

- **WHEN** a bump fails after advancing only some tickets
- **THEN** the board refetches and shows exactly the statuses the server holds, with no stuck
  optimistic state

### Requirement: My-station mode

The board SHALL offer a single-station list mode ("my station") that shows only the selected
station's unfinished work as a dense, oldest-first list optimized for a cook at one station, with
the same tap-to-advance behavior as the docket view.

#### Scenario: Cook works a single station

- **WHEN** the user enters my-station mode for a selected station
- **THEN** only that station's unfinished tickets are listed oldest-first and tapping one
  advances it forward

### Requirement: Expo alert panel

The board SHALL offer an expo panel that lists orders sorted by severity (most overdue first),
showing for each order its waiting time, alert severity, and which stations still owe work, so an
expeditor can see at a glance what is blocking the pass.

#### Scenario: Expeditor sees blocking stations

- **WHEN** an order has some dishes ready and one station's dish still `pending` past its
  warning threshold
- **THEN** the expo panel lists the order with its severity and names the station still owing
  work

### Requirement: Recipe affordances hidden

While no backend source for recipes exists, the board SHALL NOT render recipe affordances
(drawer, buttons) in production; mock recipe data SHALL NOT be shown to end users.

#### Scenario: No recipe UI in production

- **WHEN** a cook uses the board at `/kitchen`
- **THEN** no recipe drawer or recipe button is rendered anywhere on the board
