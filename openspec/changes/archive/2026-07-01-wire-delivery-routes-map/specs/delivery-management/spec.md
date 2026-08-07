# delivery-management (delta)

## MODIFIED Requirements

### Requirement: Manage delivery routes

The system SHALL allow authorized users to create, list, update and deactivate delivery routes for a branch, each with a name, a structured list of covered zone names (≤20 zones, each ≤60 chars, empty by default), an optional ring color (hex), a band position (its ring order around the business, assigned as next-available on creation), and an active flag.

#### Scenario: Create a route

- **WHEN** an authorized user creates a route for a branch of the current tenant
- **THEN** the route is persisted active, takes the branch's next band position, and is returned
  with its zones, color and position

#### Scenario: Update zones and color

- **WHEN** an authorized user updates a route's zone list and color
- **THEN** the route reflects the new values and an oversized zone list is rejected with a
  validation error

#### Scenario: Reject unknown branch

- **WHEN** a user creates a route for a `branch_id` not in the current tenant
- **THEN** the system responds 404 Not Found

#### Scenario: List routes for a branch

- **WHEN** an authorized user lists routes for a branch
- **THEN** only that branch's routes are returned, ordered by band position

### Requirement: Manage route drivers

The system SHALL allow authorized users to assign an employee as a driver of a route, list a route's drivers, and remove a driver. The employee and route MUST belong to the current tenant; the same route-employee pair MUST NOT be assigned twice. The route-driver listing SHALL include each driver's derived status: `inactive` when the assignment is inactive, `on_route` when the employee has a dispatch run in progress (`preparing` or `in_transit`), otherwise `available` — derived at read time, never stored.

#### Scenario: Assign a driver to a route

- **WHEN** an authorized user assigns an existing employee to an existing route
- **THEN** the route-driver mapping is persisted active

#### Scenario: Reject duplicate driver assignment

- **WHEN** a user assigns an employee already assigned to that route
- **THEN** the system responds with a conflict error

#### Scenario: Remove a driver from a route

- **WHEN** an authorized user removes an existing route-driver mapping
- **THEN** the mapping no longer exists

#### Scenario: Driver status reflects dispatch activity

- **WHEN** a route's drivers are listed while one of them has a run in `in_transit`
- **THEN** that driver's status reads `on_route` and a run-free active driver reads `available`

## ADDED Requirements

### Requirement: Branch delivery settings

The system SHALL keep at most one delivery-settings row per branch holding the business
coordinates (latitude/longitude, nullable until first set) and the uniform ring band width
`ring_step_km` (default 1.0, valid range 0.5–5.0). Reading a branch's settings SHALL lazily
create the default row so clients always receive one shape; updates (coordinates, step) SHALL
require the manage permission and validate the step range. Tenancy and branch ownership SHALL be
enforced as everywhere else in the module.

#### Scenario: First read creates defaults

- **WHEN** an authorized user reads settings for a branch that has none
- **THEN** a row with null coordinates and the default step is created and returned

#### Scenario: Set the business location

- **WHEN** an authorized user updates the settings with latitude/longitude
- **THEN** subsequent reads return those coordinates

#### Scenario: Step out of range is rejected

- **WHEN** an update carries `ring_step_km` outside 0.5–5.0
- **THEN** the request fails validation and nothing is stored
