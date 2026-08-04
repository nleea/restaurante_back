# frontend-delivery-dispatch (delta)

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Manage deliveries

The DispatchView SHALL list deliveries by status and let an authorized user create a delivery for an
open order (selecting the order and capturing a required address, optional neighborhood and optional
notes); creation SHALL require the `delivery.manage` permission. A second delivery for the same
order SHALL surface a friendly conflict message.

#### Scenario: Create a delivery

- **WHEN** a user with `delivery.manage` creates a delivery for an open order with an address
- **THEN** the delivery appears in the list in status `pending`

#### Scenario: Duplicate delivery is rejected friendly

- **WHEN** a user creates a delivery for an order that already has one
- **THEN** the screen shows a friendly "ese pedido ya tiene un domicilio" message and no duplicate is
  created

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
