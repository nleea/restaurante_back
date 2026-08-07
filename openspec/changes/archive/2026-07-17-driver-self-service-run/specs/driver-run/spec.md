## ADDED Requirements

### Requirement: Driver resolves their own delivery identity

The system SHALL let an authenticated driver resolve their own `Employee` identity from their auth session (via the existing staff self endpoint), so that every driver-facing delivery action is scoped to that employee without the driver supplying an `employee_id`. A driver action SHALL derive the employee from the session, never from client input.

#### Scenario: The session maps to an employee
- **WHEN** an authenticated user whose account is linked to an active employee opens the driver console
- **THEN** the system resolves their employee identity from the session and scopes subsequent driver actions to it

#### Scenario: A user with no employee link cannot act as a driver
- **WHEN** an authenticated user with no linked employee calls a driver endpoint
- **THEN** the system responds with a not-found or forbidden error and performs no action

### Requirement: Driver opens their own despacho

A driver holding `delivery.drive` SHALL be able to open a despacho for themselves without a dispatcher. Opening SHALL create a run owned by the driver (`employee_id = the driver`, status `preparing`) on a route the driver actively drives, and SHALL pull the branch's eligible pending deliveries onto that run (`delivery_status == pending` and unassigned, same branch), leaving them `assigned` and the run ready to depart.

If the driver actively drives exactly one route, that route SHALL be used. If the driver drives more than one route, the driver SHALL choose the route. If the driver drives no route, opening SHALL be rejected with a clear error.

A driver SHALL NOT have more than one active (`preparing` or `in_transit`) run at a time; opening while one is active SHALL return the existing active run rather than creating a second.

#### Scenario: Driver self-opens and pulls pending deliveries
- **WHEN** a driver with one active route and no active run opens a despacho, and the branch has pending unassigned deliveries
- **THEN** a `preparing` run owned by the driver is created and the eligible pending deliveries are assigned to it

#### Scenario: Opening with an already-active run is idempotent
- **WHEN** a driver who already has an active run opens a despacho
- **THEN** the system returns the existing active run and creates no second run

#### Scenario: Driver with no route cannot open
- **WHEN** a driver who drives no active route opens a despacho
- **THEN** the system responds with a validation error and creates no run

#### Scenario: Driver can read the routes they may open with
- **WHEN** a driver requests the routes they actively drive
- **THEN** the system returns their active routes in their branch, so a multi-route driver can choose one when opening a despacho

#### Scenario: A delivery already assigned is not pulled
- **WHEN** a driver self-opens and some branch deliveries are already assigned to another run
- **THEN** only pending unassigned deliveries are pulled, and the already-assigned ones are left untouched

### Requirement: Driver removes a wrongly-pulled delivery before departing

While the driver's run is still `preparing`, the driver SHALL be able to remove (unassign) a delivery they pulled, returning it to the pending pool (`delivery_status == pending`, no run/route), so a drop grabbed by mistake goes back to others. Removal SHALL be allowed only on the driver's own `preparing` run; once departed, deliveries SHALL NOT be removed this way.

#### Scenario: Remove a pulled delivery before departure
- **WHEN** a driver removes a delivery from their own `preparing` run
- **THEN** the delivery returns to `pending` with no run or route, available to be pulled again

#### Scenario: Cannot remove after departure
- **WHEN** a driver tries to remove a delivery from a run that has departed
- **THEN** the system responds with a conflict error and the delivery is unchanged

### Requirement: Driver reads their own active run with enriched stops

A driver holding `delivery.drive` SHALL be able to read **their own** active run in one call, returning the run and its deliveries ordered by `route_position`. Each stop SHALL be enriched with an order summary read from the orders module — order code, customer name and phone, item lines (name and quantity), total, and payment method with paid/unpaid state — so the driver app does not require branch-wide order read access. When the driver has no active run, the read SHALL return an empty result.

#### Scenario: Read my active run enriched
- **WHEN** a driver with an active run reads their run
- **THEN** the system returns that run with its deliveries ordered by route position, each carrying its order code, customer, phone, items, total, and payment method/state

#### Scenario: No active run
- **WHEN** a driver with no active run reads their run
- **THEN** the system returns an empty result rather than another driver's run

#### Scenario: The read is limited to the caller
- **WHEN** a driver reads "my run"
- **THEN** only a run owned by the calling driver is ever returned

### Requirement: Driver works their own run lifecycle

A driver holding `delivery.drive` SHALL be able to depart their own `preparing` run, mark their own in-transit deliveries delivered or not delivered, and finish their own `in_transit` run — using the same state machine as the dispatcher path. Every such action SHALL verify the run (or the delivery's run) is owned by the calling driver; acting on another driver's run SHALL be rejected.

#### Scenario: Driver departs their own run
- **WHEN** a driver departs their own `preparing` run
- **THEN** the run becomes `in_transit` and its assigned deliveries become `in_transit`

#### Scenario: Driver marks their own delivery
- **WHEN** a driver marks an `in_transit` delivery of their own run as delivered or not delivered
- **THEN** the delivery reaches the corresponding terminal state

#### Scenario: Driver cannot act on another driver's run
- **WHEN** a driver departs, finishes, or marks a delivery of a run owned by a different employee
- **THEN** the system responds with a forbidden or not-found error and nothing changes

#### Scenario: Driver finishes their own run
- **WHEN** a driver finishes their own `in_transit` run
- **THEN** the run becomes `finished`
