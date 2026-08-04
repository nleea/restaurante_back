# frontend-delivery-dispatch

## Purpose

The dispatch frontend — the operational client for the delivery flow of the backend `/delivery`
module, building on the route + driver configuration (`frontend-delivery`). It is a three-pane
dispatch board — stats/filters rail, main list with two areas (**Domicilios** and **Despachos**),
and a detail pane. The flow turns an open order
into a per-order delivery record (address-centric), builds a dispatch run from a route and one of its
drivers, and drives the two-entity lifecycle — a delivery goes pending→assigned→in_transit→delivered/
not_delivered, a run goes preparing→in_transit→finished, and departing a run cascades its assigned
deliveries to in_transit. The deliveries/runs list endpoints are branch-scoped (a required `branch_id`
plus an optional status filter), so the board shows the active branch's records and never mixes two
branches' work; create flows source open orders and routes from the same active branch, and the
server derives a record's branch (a delivery's from its order, a run's from its route) rather than
taking it from the request. Records are id-only — a delivery names an `order_id` plus an
address, a run names a route and a driver — so labels are resolved from the delivery routes, staff,
and orders data, with the address as a delivery's primary identity. Each lifecycle action is offered
only in the state that allows it, and mutations are write-through (depart refetches both runs and
deliveries to reflect the cascade). The screen is reached with `delivery.read`; create-delivery
requires `delivery.address` (the narrow code held by whoever takes the order), create-run requires
`delivery.manage`, and the assign/depart/mark/finish transitions require `delivery.assign` — UX
gating only, the backend enforces authorization independently. Cash-on-
delivery, auto-assignment/optimization, live GPS, order-status reflection, and editing a run's
route/driver after creation are out of scope for this slice.
## Requirements
### Requirement: Dispatch service layer

The Delivery API service SHALL expose typed functions covering the dispatch endpoints of
`/delivery`: deliveries — create (`POST /deliveries`), list (`GET /deliveries`, **required
`branch_id`**, optional `status_filter`), get by order (`GET /orders/{orderId}/delivery`), and
update address (`PATCH /deliveries/{id}`); runs — create (`POST /runs`), list (`GET /runs`,
**required `branch_id`**, optional `status_filter`), and get (`GET /runs/{id}`); and the
lifecycle — assign a delivery to a run (`POST /deliveries/{id}/assign`), depart a run
(`POST /runs/{id}/depart`), mark a delivery delivered or not (`POST /deliveries/{id}/mark-delivered`
with `{ delivered }`), and finish a run (`POST /runs/{id}/finish`).

The list calls SHALL NOT be tenant-wide: deliveries and runs belong to a branch, like the routes
and settings beside them, and the board of a multi-branch tenant SHALL NOT mix them.

The create calls SHALL NOT carry a `branch_id` — the server derives a delivery's branch from its
order and a run's from its route.

#### Scenario: Create a delivery for an order

- **WHEN** `createDelivery({ order_id, address_text, neighborhood? })` is called
- **THEN** the delivery is created for that order and the branch is taken from the order, not
  from the request

#### Scenario: List deliveries by status

- **WHEN** `listDeliveries(branchId, 'in_transit')` is called
- **THEN** it GETs `/delivery/deliveries` passing `branch_id` and `status_filter=in_transit` and
  resolves with the array of `Delivery`

#### Scenario: Listing without a branch is not possible

- **WHEN** the deliveries or runs list is requested
- **THEN** a `branch_id` is always carried, and only that branch's records come back

#### Scenario: Create a run

- **WHEN** `createRun({ delivery_route_id, employee_id })` is called
- **THEN** it POSTs `/delivery/runs` and resolves with the created `Run` in status `preparing`,
  whose branch is taken from the route

#### Scenario: Assign a delivery to a run

- **WHEN** `assignDelivery(deliveryId, { delivery_run_id })` is called
- **THEN** it POSTs `/delivery/deliveries/{deliveryId}/assign` and resolves with the updated
  `Delivery`

#### Scenario: Depart and finish a run

- **WHEN** `departRun(runId)` then `finishRun(runId)` are called
- **THEN** they POST `/delivery/runs/{runId}/depart` and `/delivery/runs/{runId}/finish`

#### Scenario: Mark a delivery delivered or not delivered

- **WHEN** `markDelivered(deliveryId, true)` or `markDelivered(deliveryId, false)` is called
- **THEN** it POSTs `/delivery/deliveries/{deliveryId}/mark-delivered` with `{ delivered: true|false }`

### Requirement: Dispatch store

The Dispatch store SHALL hold the **active branch's** deliveries and runs, group a run's deliveries by
`delivery_run_id`, and group deliveries by status. Lifecycle mutations (create delivery, create run,
assign, depart, mark delivered, finish) SHALL be write-through: after a successful call the store
refetches the affected collections so server state — including cascaded transitions — is shown
verbatim.

Because the write-through refetches carry no branch of their own, the store SHALL remember the branch
it was last loaded for and reuse it. A refetch with no branch loaded SHALL be a no-op rather than a
tenant-wide fetch.

#### Scenario: Load deliveries and runs

- **WHEN** the store loads dispatch data for a branch
- **THEN** `deliveries` and `runs` hold that branch's records and the board can render them by status

#### Scenario: A mutation refetches within the same branch

- **WHEN** any lifecycle mutation succeeds
- **THEN** the store refetches using the branch it was loaded for, and records of another branch never
  enter the collections

#### Scenario: Departing a run cascades to its deliveries

- **WHEN** a `preparing` run is departed
- **THEN** the store refetches runs and deliveries so the run shows `in_transit` and its assigned
  deliveries show `in_transit`

#### Scenario: Marking a delivery refreshes it

- **WHEN** a delivery is marked delivered or not delivered
- **THEN** the store refetches deliveries so the delivery shows `delivered` or `not_delivered`

### Requirement: Label resolution for dispatch records

The store SHALL resolve human labels for dispatch records — whose deliveries carry only `order_id`
plus an address and whose runs carry only `delivery_route_id` and `employee_id` — namely a delivery's
address (and a best-effort order reference from the orders data) and a run's route name (from the
delivery routes) and driver name (from staff), and SHALL degrade gracefully to a short reference when
a label cannot be resolved.

#### Scenario: Run shows route and driver names

- **WHEN** a run's `delivery_route_id` and `employee_id` map to a known route and employee
- **THEN** the run shows the route name and driver name

#### Scenario: Delivery is identified by address

- **WHEN** a delivery is rendered
- **THEN** it shows its address (and neighborhood when present), degrading to a short order reference
  for the order link

### Requirement: Manage deliveries

The DispatchView SHALL list deliveries by status and let an authorized user create a delivery for an
open order (selecting the order and capturing a required address, optional neighborhood and optional
notes), and optionally capture the delivery's coordinates by tapping a mini-map (centered on the
branch's business location) or by pasting a shared location (a `lat,lng` pair or a Google Maps
link), with the resolved point shown on the mini-map for confirmation before saving; creation SHALL
require the `delivery.address` permission. A second delivery for the same order SHALL surface a
friendly conflict message. Deliveries SHALL show whether they carry a location, and a delivery
without one (or with a wrong one) SHALL be locatable/correctable later from the board's detail pane
through the same picker.

Address capture is no longer exclusive to the board: the order-taking surfaces capture it too (see
`frontend-salon`). The board's creation flow SHALL remain available as the fallback for orders that
reached dispatch without an address, and SHALL continue to exclude orders that already have a
delivery.

#### Scenario: Create a delivery

- **WHEN** a user with `delivery.address` creates a delivery for an open order with an address
- **THEN** the delivery appears in the list in status `pending`

#### Scenario: Capture the point by tapping the mini-map

- **WHEN** the user taps a point on the form's mini-map before saving
- **THEN** the created delivery carries those coordinates and appears as a dot on the coverage map

#### Scenario: Paste a shared location

- **WHEN** the user pastes a `lat,lng` pair or a Google Maps link from a customer's shared location
- **THEN** the point resolves onto the mini-map for confirmation and is saved with the delivery; an
  unparseable paste explains what formats work instead of failing silently

#### Scenario: Add the location later

- **WHEN** a user with `delivery.address` opens a location-less delivery's detail and picks a point
- **THEN** the delivery is updated with the coordinates and the coverage map's "sin ubicación"
  count decreases

#### Scenario: Duplicate delivery is rejected friendly

- **WHEN** a user creates a delivery for an order that already has one
- **THEN** the screen shows a friendly "ese pedido ya tiene un domicilio" message and no duplicate is
  created

#### Scenario: An order that arrived with its address is not offered for creation

- **WHEN** an order's address was captured at the Salón or the comanda, so it already has a delivery
- **THEN** the board's "Nuevo domicilio" order picker does not offer that order

### Requirement: Manage runs

The DispatchView SHALL list runs by status and let an authorized user create a run through a
two-step flow — first choosing an available driver (busy and inactive drivers are shown but not
selectable), then choosing the route (defaulting to the driver's route) and selecting unassigned
deliveries to include; creation SHALL require the `delivery.manage` permission. A run SHALL show
its assigned deliveries, and while the run is `preparing` the user SHALL be able to add further
unassigned deliveries to it.

#### Scenario: Create a run

- **WHEN** a user with `delivery.manage` completes both steps with a driver, route and at least one
  delivery
- **THEN** the run appears in status `preparing` with the selected deliveries `assigned` to it

#### Scenario: Busy driver is not selectable

- **WHEN** the driver step lists a driver who has a run in `preparing` or `in_transit`
- **THEN** that driver is visible but cannot be selected

#### Scenario: Run lists its deliveries

- **WHEN** deliveries are assigned to a run
- **THEN** the run's detail lists those deliveries

#### Scenario: Add a delivery to a preparing run

- **WHEN** a user with `delivery.assign` adds an unassigned delivery to a `preparing` run from the
  run detail
- **THEN** the delivery becomes `assigned` and joins the run's stop list

### Requirement: Dispatch lifecycle

The DispatchView SHALL drive the dispatch lifecycle, each transition gated by the `delivery.assign`
permission and offered only in the state that allows it: assign a `pending` delivery to a `preparing`
run; depart a `preparing` run (moving it and its assigned deliveries to `in_transit`); mark an
`in_transit` delivery `delivered` or `not_delivered`; and finish an `in_transit` run. An out-of-order
transition SHALL surface a friendly conflict message.

#### Scenario: Assign a delivery to a preparing run

- **WHEN** a user with `delivery.assign` assigns a `pending` delivery to a `preparing` run
- **THEN** the delivery's status becomes `assigned` and it is listed under that run

#### Scenario: Depart a run

- **WHEN** a user with `delivery.assign` departs a `preparing` run
- **THEN** the run becomes `in_transit` and its assigned deliveries become `in_transit`

#### Scenario: Mark a delivery delivered

- **WHEN** a user with `delivery.assign` marks an `in_transit` delivery delivered
- **THEN** the delivery's status becomes `delivered`

#### Scenario: Finish a run

- **WHEN** a user with `delivery.assign` finishes an `in_transit` run
- **THEN** the run becomes `finished`

#### Scenario: Out-of-order transition is rejected friendly

- **WHEN** a user attempts a transition the current state does not allow (e.g. assigning to a departed
  run)
- **THEN** the screen shows a friendly conflict message and no change is made

### Requirement: Permission gating and navigation

The Dispatch screen SHALL be reachable at `/dispatch` only for authenticated users with
`delivery.read`, exposed via a navigation entry; the create-delivery and create-run controls SHALL
require `delivery.manage`, and the assign/depart/mark/finish controls SHALL require
`delivery.assign`. This gating is UX — the backend enforces authorization independently.

#### Scenario: Read-only dispatch user

- **WHEN** the current user has `delivery.read` but neither `delivery.manage` nor `delivery.assign`
- **THEN** the deliveries and runs are visible read-only and no create or lifecycle actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `delivery.read` navigates to `/dispatch`
- **THEN** the router redirects them to the forbidden view

### Requirement: Dispatch board layout

The Dispatch screen SHALL be a three-pane board: a rail with stats and filters, the main list
(Domicilios or Despachos tab), and a detail pane for the selected record. On viewports below the
desktop breakpoint the rail SHALL collapse behind a "Filtros" toggle, and the list/detail SHALL
follow the app's master–detail pattern (list fills the screen; selecting drills into a full-screen
detail with a back affordance).

#### Scenario: Desktop shows three panes

- **WHEN** the board renders at desktop width
- **THEN** rail, list and detail are visible simultaneously and selecting a record updates the
  detail in place

#### Scenario: Mobile drill-down

- **WHEN** a record is selected at mobile width
- **THEN** the detail replaces the list full-screen and a back control returns to the list

### Requirement: Dispatch stats and filters

The board SHALL show live counts (en ruta, pendientes, entregados hoy, total hoy) computed from
the loaded deliveries, and SHALL filter the active list by status, route, driver, and an address
search string; filters combine (AND) and apply live.

#### Scenario: Filters combine

- **WHEN** the user selects a status, a route and types an address fragment
- **THEN** the list shows only records matching all three

#### Scenario: Stats reflect loaded data

- **WHEN** a delivery transitions to `delivered`
- **THEN** the "entregados hoy" count increases without a page reload

### Requirement: Delivery lifecycle timeline

The delivery detail SHALL render the lifecycle as a vertical timeline (Pedido recibido → Asignado →
En ruta → Entregado/No entregado) marking completed, active and pending steps. Times come from the
available timestamps: `created_at` (recibido), the run's `departed_at` (en ruta) and
`delivered_at`; the Asignado step renders without a time.

#### Scenario: In-transit delivery timeline

- **WHEN** an `in_transit` delivery is selected
- **THEN** recibido and en ruta show their times, en ruta is the active step, and entregado is
  pending

### Requirement: Run stop strip and progress

Each run card and the run detail SHALL render its deliveries as an ordered segmented strip — one
segment per delivery, colored by that delivery's state — together with a "N de M entregados"
progress label. Selecting a stop in the run detail SHALL navigate to that delivery's detail.

#### Scenario: Strip reflects per-stop state

- **WHEN** a run has one `delivered` and two `in_transit` deliveries
- **THEN** its strip shows one success segment and two in-progress segments, and the label reads
  "1 de 3 entregados"

### Requirement: Overdue delivery heat

Open deliveries (`pending`, `assigned`, `in_transit`) SHALL surface elapsed time since
`created_at` and SHALL escalate a visual heat treatment at 35 and 50 minutes waiting, consistent
with the KDS heat semantics. Delivered and not-delivered records show no heat.

#### Scenario: Overdue delivery glows

- **WHEN** an open delivery has waited 50+ minutes since `created_at`
- **THEN** its card shows the hot treatment

### Requirement: Delivery notes

The delivery detail SHALL let a user with `delivery.manage` read and edit the delivery's notes,
persisting through the delivery update endpoint and confirming the save.

#### Scenario: Save a note

- **WHEN** a user with `delivery.manage` edits the notes and saves
- **THEN** the note is persisted and a confirmation is shown

### Requirement: Assign-to-run flow

The board SHALL offer assignment only through runs: an unassigned (`pending`) delivery's primary
action opens a picker of `preparing` runs (with a shortcut to create a new run pre-seeded with
that delivery), and an `assigned` delivery MAY be moved to a different `preparing` run through the
same picker. No control SHALL offer assigning a driver directly to a delivery.

#### Scenario: Assign a pending delivery via the picker

- **WHEN** a user with `delivery.assign` picks a `preparing` run for a `pending` delivery
- **THEN** the delivery becomes `assigned` and appears in that run's stop list

#### Scenario: Move an assigned delivery

- **WHEN** a user with `delivery.assign` picks a different `preparing` run for an `assigned`
  delivery
- **THEN** the delivery moves to the new run and its route follows the run's route

### Requirement: Dispatch board reflects the open cash session

The dispatch board SHALL show only the deliveries the backend returns for the branch's open cash session, and SHALL present a clear "caja cerrada" empty state when there is no open session (instead of a blank or misleading empty board).

#### Scenario: Board shows only the current shift

- **WHEN** the dispatcher opens the board for a branch with an open cash session
- **THEN** only that session's deliveries are shown, not older ones

#### Scenario: Closed-caja state

- **WHEN** the dispatcher opens the board for a branch with no open cash session
- **THEN** the board shows a "caja cerrada" state making clear no shift is active

