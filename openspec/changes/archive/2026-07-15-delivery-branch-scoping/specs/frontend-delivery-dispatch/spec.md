## MODIFIED Requirements

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
