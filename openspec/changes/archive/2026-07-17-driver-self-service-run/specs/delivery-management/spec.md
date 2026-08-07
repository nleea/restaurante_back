## MODIFIED Requirements

### Requirement: Create dispatch runs

The system SHALL allow a dispatch run for a route and a driver to be created by **either** of two paths: an authorized dispatcher (`delivery.manage`) creating a run for a driver, or the driver themselves (`delivery.drive`) creating a run for their own identity. In both paths the driver MUST be an active driver assigned to that route, and a run starts in state `preparing`. When the driver self-creates, `employee_id` SHALL be the calling driver, never a client-supplied value.

#### Scenario: Create a run with a valid driver
- **WHEN** a dispatcher creates a run for a route and a driver assigned to that route
- **THEN** the run is created in state `preparing`

#### Scenario: Reject a run whose driver is not assigned to the route
- **WHEN** a user creates a run with an employee who is not an active driver of the route
- **THEN** the system responds with a validation error or not-found for the driver

#### Scenario: Driver self-creates their own run
- **WHEN** a driver holding `delivery.drive` who actively drives a route opens a despacho
- **THEN** a `preparing` run is created with the driver as its `employee_id`

### Requirement: Assignment and delivery lifecycle

The system SHALL support an explicit delivery lifecycle. Assigning a delivery to a `preparing` run sets the delivery's route and run and moves it to `assigned`. Departing a run moves it `preparing → in_transit` (stamping `departed_at`) and moves its `assigned` deliveries to `in_transit`. A delivery can then be marked `delivered` or `not_delivered` (stamping `delivered_at`); marking `not_delivered` SHALL accept and persist an optional reason (from a fixed list) and an optional free-text comment. Finishing a run moves it `in_transit → finished`. Backward or out-of-order transitions SHALL be rejected.

A delivery SHALL be assignable only to a run of **its own branch**. A cross-branch assignment SHALL be rejected as a conflict, leaving both records untouched.

#### Scenario: Assign a delivery to a run
- **WHEN** an authorized user assigns a `pending` delivery to a `preparing` run
- **THEN** the delivery's run and route are set and its status becomes `assigned`

#### Scenario: Reject assigning to a departed run
- **WHEN** a user assigns a delivery to a run that is not `preparing`
- **THEN** the system responds with a conflict error

#### Scenario: Reject assigning to a run of another branch
- **WHEN** a user assigns a delivery of branch A to a run of branch B
- **THEN** the system responds with a conflict error and neither the delivery nor the run changes

#### Scenario: Depart a run
- **WHEN** an authorized user departs a `preparing` run
- **THEN** the run becomes `in_transit` with `departed_at` set
- **AND** its `assigned` deliveries become `in_transit`

#### Scenario: Mark a delivery delivered
- **WHEN** an authorized user marks an `in_transit` delivery as delivered
- **THEN** its status becomes `delivered` with `delivered_at` set

#### Scenario: Mark a delivery not delivered with a reason
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered with a reason and optional comment
- **THEN** its status becomes `not_delivered` with `delivered_at` set and the reason (and comment, if any) persisted

#### Scenario: Mark a delivery not delivered without a reason
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered without a reason
- **THEN** its status becomes `not_delivered` with `delivered_at` set and no reason recorded

#### Scenario: Finish a run
- **WHEN** an authorized user finishes an `in_transit` run
- **THEN** the run becomes `finished` with `finished_at` set

#### Scenario: Reject finishing a non-in-transit run
- **WHEN** a user finishes a run that is not `in_transit`
- **THEN** the system responds with a conflict error

### Requirement: RBAC protection of delivery endpoints

The system SHALL require `delivery.read` for read endpoints, `delivery.manage` for managing routes, route drivers, branch delivery settings and creating runs, `delivery.address` for reading and writing a single order's delivery record (create and update), and `delivery.assign` for dispatcher-driven assignment and lifecycle transitions (assign, depart, mark delivered/not delivered, finish).

The system SHALL additionally define `delivery.drive` for driver self-service. A holder of `delivery.drive` SHALL be able to open, read, depart, finish, and mark deliveries on **their own** run — every such action verifying the run (or the delivery's run) is owned by the calling driver — WITHOUT holding `delivery.assign` or `delivery.manage`. A holder of `delivery.drive` SHALL NOT be able to act on another driver's run, create a run for a different driver, or manage routes, route drivers, or branch delivery settings.

`delivery.address` SHALL exist so the address can be captured by whoever takes the order without granting delivery administration: a holder of `delivery.address` alone SHALL NOT be able to edit routes, route drivers, branch delivery settings, or create runs.

For backward compatibility with roles provisioned before this split, the delivery-record endpoints SHALL accept **either** of two codes: reading an order's delivery record SHALL accept `delivery.address` or `delivery.read`; creating or updating a delivery record SHALL accept `delivery.address` or `delivery.manage`.

#### Scenario: Read without permission
- **WHEN** a user lacking `delivery.read` calls a delivery read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Manage without permission
- **WHEN** a user lacking `delivery.manage` tries to create a route or a run
- **THEN** the system responds 403 Forbidden

#### Scenario: Assign without permission
- **WHEN** a user lacking `delivery.assign` tries to assign a delivery or advance the lifecycle via the dispatcher endpoints
- **THEN** the system responds 403 Forbidden

#### Scenario: Driver self-service without the driver permission
- **WHEN** a user lacking `delivery.drive` calls a driver self-service endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Driver drives only their own run
- **WHEN** a holder of `delivery.drive` (without `delivery.assign`) departs, finishes, or marks a delivery on a run they own
- **THEN** the requests succeed
- **AND** the same actions on a run owned by a different driver respond 403 Forbidden or 404 Not Found

#### Scenario: Address permission writes a delivery record without delivery administration
- **WHEN** a user holding `delivery.address` but neither `delivery.manage` nor `delivery.read` creates or updates a delivery record for an order, and reads that order's delivery record
- **THEN** those requests succeed

#### Scenario: Address permission does not grant delivery administration
- **WHEN** a user holding `delivery.address` but not `delivery.manage` tries to create or edit a route, edit route drivers, patch branch delivery settings, or create a run
- **THEN** the system responds 403 Forbidden

#### Scenario: A pre-existing manage-only role keeps writing delivery records
- **WHEN** a user holding `delivery.manage` but not `delivery.address` creates or updates a delivery record
- **THEN** the request succeeds

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

### Requirement: Base roles for delivery address capture

The permission catalog SHALL define `delivery.address` in the `delivery` module, and the base roles SHALL grant it to the roles that take orders — `waiter`, `cashier`, `manager` and `admin` — so the address can be captured at the moment the order is taken.

The permission catalog SHALL also define `delivery.drive` in the `delivery` module, and the base roles SHALL grant it to the `courier` role so a courier can open and work their own despacho without dispatcher permissions.

The `courier` base role SHALL NOT hold `delivery.address`.

Provisioning SHALL remain additive and idempotent: adding these codes SHALL NOT require a schema migration for the catalog, and re-running the RBAC seed SHALL insert the permissions and grant them to the base roles without disturbing tenant-custom roles.

#### Scenario: Order-taking base roles gain the permission
- **WHEN** the RBAC seed runs against an installation provisioned before this change
- **THEN** `delivery.address` exists in the permission catalog and the `waiter`, `cashier` and `manager` base roles hold it

#### Scenario: Couriers gain the driver permission
- **WHEN** the RBAC seed runs
- **THEN** `delivery.drive` exists in the permission catalog and the `courier` base role holds it

#### Scenario: Seeding twice changes nothing further
- **WHEN** the RBAC seed runs a second time
- **THEN** no duplicate permission or role grant is created

#### Scenario: Couriers do not author addresses
- **WHEN** the base roles are provisioned
- **THEN** the `courier` role does not hold `delivery.address`
