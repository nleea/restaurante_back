## ADDED Requirements

### Requirement: Dispatch service layer

The Delivery API service SHALL expose typed functions covering the dispatch endpoints of
`/delivery`: deliveries — create (`POST /deliveries`), list (`GET /deliveries`, optional
`status_filter`), get by order (`GET /orders/{orderId}/delivery`), and update address
(`PATCH /deliveries/{id}`); runs — create (`POST /runs`), list (`GET /runs`, optional
`status_filter`), and get (`GET /runs/{id}`); and the lifecycle — assign a delivery to a run
(`POST /deliveries/{id}/assign`), depart a run (`POST /runs/{id}/depart`), mark a delivery
delivered or not (`POST /deliveries/{id}/mark-delivered` with `{ delivered }`), and finish a run
(`POST /runs/{id}/finish`).

#### Scenario: Create a delivery for an order

- **WHEN** `createDelivery({ order_id, address_text, neighborhood? })` is called
- **THEN** it POSTs `/delivery/deliveries` and resolves with the created `Delivery` in status
  `pending`

#### Scenario: List deliveries by status

- **WHEN** `listDeliveries('in_transit')` is called
- **THEN** it GETs `/delivery/deliveries` passing `status_filter=in_transit` and resolves with the
  array of `Delivery`

#### Scenario: Create a run

- **WHEN** `createRun({ delivery_route_id, employee_id })` is called
- **THEN** it POSTs `/delivery/runs` and resolves with the created `Run` in status `preparing`

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

The Dispatch store SHALL hold the tenant's deliveries and runs, group a run's deliveries by
`delivery_run_id`, and group deliveries by status. Lifecycle mutations (create delivery, create run,
assign, depart, mark delivered, finish) SHALL be write-through: after a successful call the store
refetches the affected collections so server state — including cascaded transitions — is shown
verbatim.

#### Scenario: Load deliveries and runs

- **WHEN** the store loads dispatch data
- **THEN** `deliveries` and `runs` hold the tenant's records and the board can render them by status

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
open order (selecting the order and capturing a required address and optional neighborhood); creation
SHALL require the `delivery.manage` permission. A second delivery for the same order SHALL surface a
friendly conflict message.

#### Scenario: Create a delivery

- **WHEN** a user with `delivery.manage` creates a delivery for an open order with an address
- **THEN** the delivery appears in the list in status `pending`

#### Scenario: Duplicate delivery is rejected friendly

- **WHEN** a user creates a delivery for an order that already has one
- **THEN** the screen shows a friendly "ese pedido ya tiene un domicilio" message and no duplicate is
  created

### Requirement: Manage runs

The DispatchView SHALL list runs by status and let an authorized user create a run by choosing a
route and one of that route's drivers; creation SHALL require the `delivery.manage` permission. A run
SHALL show its assigned deliveries.

#### Scenario: Create a run

- **WHEN** a user with `delivery.manage` creates a run for a route and one of its drivers
- **THEN** the run appears in status `preparing`

#### Scenario: Run lists its deliveries

- **WHEN** deliveries are assigned to a run
- **THEN** the run's detail lists those deliveries

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
