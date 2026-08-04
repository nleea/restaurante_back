## ADDED Requirements

### Requirement: Tenant and branch isolation for delivery

The system SHALL scope every delivery read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate routes, runs or deliveries of another tenant.

#### Scenario: Tenant cannot see another tenant's routes
- **WHEN** a request for tenant A lists delivery routes
- **THEN** only routes whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a route id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a delivery endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage delivery routes

The system SHALL allow authorized users to create, list, update and deactivate delivery routes for a branch, each with a name, optional covered zones, and an active flag.

#### Scenario: Create a route
- **WHEN** an authorized user creates a route for a branch of the current tenant
- **THEN** the route is persisted active and returned

#### Scenario: Reject unknown branch
- **WHEN** a user creates a route for a `branch_id` not in the current tenant
- **THEN** the system responds 404 Not Found

#### Scenario: List routes for a branch
- **WHEN** an authorized user lists routes for a branch
- **THEN** only that branch's routes are returned

### Requirement: Manage route drivers

The system SHALL allow authorized users to assign an employee as a driver of a route, list a route's drivers, and remove a driver. The employee and route MUST belong to the current tenant; the same route-employee pair MUST NOT be assigned twice.

#### Scenario: Assign a driver to a route
- **WHEN** an authorized user assigns an existing employee to an existing route
- **THEN** the route-driver mapping is persisted active

#### Scenario: Reject duplicate driver assignment
- **WHEN** a user assigns an employee already assigned to that route
- **THEN** the system responds with a conflict error

#### Scenario: Remove a driver from a route
- **WHEN** an authorized user removes an existing route-driver mapping
- **THEN** the mapping no longer exists

### Requirement: Create a per-order delivery record

The system SHALL allow authorized users to create exactly one delivery record for an order, capturing a required address and optional neighborhood and latitude/longitude. The order MUST belong to the current tenant. A delivery starts in state `pending`.

#### Scenario: Create a delivery for an order
- **WHEN** an authorized user creates a delivery for an order with an address
- **THEN** the delivery is persisted in state `pending` and returned

#### Scenario: Reject a second delivery for the same order
- **WHEN** a user creates a delivery for an order that already has one
- **THEN** the system responds with a conflict error

#### Scenario: Reject unknown order
- **WHEN** a user creates a delivery for an `order_id` not in the current tenant
- **THEN** the system responds 404 Not Found

#### Scenario: List and view deliveries
- **WHEN** an authorized user lists deliveries (optionally filtered by status) or fetches one by order
- **THEN** only the tenant's deliveries matching the request are returned

### Requirement: Create dispatch runs

The system SHALL allow authorized users to create a dispatch run for a route and a driver. The driver MUST be an active driver assigned to that route. A run starts in state `preparing`.

#### Scenario: Create a run with a valid driver
- **WHEN** an authorized user creates a run for a route and a driver assigned to that route
- **THEN** the run is created in state `preparing`

#### Scenario: Reject a run whose driver is not assigned to the route
- **WHEN** a user creates a run with an employee who is not an active driver of the route
- **THEN** the system responds with a validation error or not-found for the driver

### Requirement: Assignment and delivery lifecycle

The system SHALL support an explicit delivery lifecycle. Assigning a delivery to a `preparing` run sets the delivery's route and run and moves it to `assigned`. Departing a run moves it `preparing → in_transit` (stamping `departed_at`) and moves its `assigned` deliveries to `in_transit`. A delivery can then be marked `delivered` or `not_delivered` (stamping `delivered_at`). Finishing a run moves it `in_transit → finished`. Backward or out-of-order transitions SHALL be rejected.

#### Scenario: Assign a delivery to a run
- **WHEN** an authorized user assigns a `pending` delivery to a `preparing` run
- **THEN** the delivery's run and route are set and its status becomes `assigned`

#### Scenario: Reject assigning to a departed run
- **WHEN** a user assigns a delivery to a run that is not `preparing`
- **THEN** the system responds with a conflict error

#### Scenario: Depart a run
- **WHEN** an authorized user departs a `preparing` run
- **THEN** the run becomes `in_transit` with `departed_at` set
- **AND** its `assigned` deliveries become `in_transit`

#### Scenario: Mark a delivery delivered
- **WHEN** an authorized user marks an `in_transit` delivery as delivered
- **THEN** its status becomes `delivered` with `delivered_at` set

#### Scenario: Mark a delivery not delivered
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered
- **THEN** its status becomes `not_delivered` with `delivered_at` set

#### Scenario: Finish a run
- **WHEN** an authorized user finishes an `in_transit` run
- **THEN** the run becomes `finished` with `finished_at` set

#### Scenario: Reject finishing a non-in-transit run
- **WHEN** a user finishes a run that is not `in_transit`
- **THEN** the system responds with a conflict error

### Requirement: RBAC protection of delivery endpoints

The system SHALL require `delivery.read` for read endpoints, `delivery.manage` for managing routes, route drivers, delivery records and creating runs, and `delivery.assign` for assignment and lifecycle transitions (assign, depart, mark delivered/not delivered, finish).

#### Scenario: Read without permission
- **WHEN** a user lacking `delivery.read` calls a delivery read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Manage without permission
- **WHEN** a user lacking `delivery.manage` tries to create a route or a run
- **THEN** the system responds 403 Forbidden

#### Scenario: Assign without permission
- **WHEN** a user lacking `delivery.assign` tries to assign a delivery or advance the lifecycle
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
