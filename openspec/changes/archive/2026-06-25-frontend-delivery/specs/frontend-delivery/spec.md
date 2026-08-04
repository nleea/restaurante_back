## ADDED Requirements

### Requirement: Delivery service layer (routes and drivers)

The Delivery API service SHALL expose typed functions covering the route slice of `/delivery`:
list routes for a branch (`GET /delivery/routes`, required `branch_id`); create a route
(`POST /delivery/routes`); update or deactivate a route (`PATCH /delivery/routes/{routeId}`, the
same endpoint editing name/zones and flipping `is_active`); list a route's drivers
(`GET /delivery/routes/{routeId}/drivers`); assign a driver
(`POST /delivery/routes/{routeId}/drivers`); and remove one
(`DELETE /delivery/routes/{routeId}/drivers/{employeeId}`).

#### Scenario: List routes for a branch

- **WHEN** `listRoutes(branchId)` is called
- **THEN** it GETs `/delivery/routes` passing `branch_id` and resolves with the array of `Route`

#### Scenario: Create a route

- **WHEN** `createRoute({ branch_id, name, covered_zones? })` is called
- **THEN** it POSTs `/delivery/routes` and resolves with the created `Route`

#### Scenario: Deactivate a route via patch

- **WHEN** `updateRoute(routeId, { is_active: false })` is called
- **THEN** it PATCHes `/delivery/routes/{routeId}` and resolves with the updated `Route`

#### Scenario: Assign a driver to a route

- **WHEN** `assignDriver(routeId, { employee_id })` is called
- **THEN** it POSTs `/delivery/routes/{routeId}/drivers` and resolves with the created `RouteDriver`

#### Scenario: Remove a driver from a route

- **WHEN** `removeDriver(routeId, employeeId)` is called
- **THEN** it DELETEs `/delivery/routes/{routeId}/drivers/{employeeId}`

### Requirement: Delivery store with branch-scoped routes

The Delivery store SHALL hold the active branch's routes and the selected route's drivers, load
routes scoped to the active branch, and resolve each driver's employee name from the staff
directory. Mutations (create/update/deactivate route, assign/remove driver) SHALL be write-through:
after a successful call the store refetches the affected collection so server state is shown
verbatim.

#### Scenario: Load routes for the active branch

- **WHEN** the store loads routes for the active branch
- **THEN** `routes` holds that branch's routes and the list can render them

#### Scenario: Creating a route refreshes the list

- **WHEN** a route is created
- **THEN** the store refetches the branch's routes so the new route appears without a manual reload

#### Scenario: Assigning a driver refreshes the route's drivers

- **WHEN** a driver is assigned to the selected route
- **THEN** the store refetches that route's drivers so the new driver appears

### Requirement: Manage delivery routes

The DeliveryView SHALL list the active branch's routes with an active filter and let an authorized
user create a route (name, optional covered zones), edit its name and zones, and deactivate or
reactivate it; these mutations SHALL require the `delivery.manage` permission.

#### Scenario: Create a route

- **WHEN** a user with `delivery.manage` submits the new-route form with a name
- **THEN** the route is created and appears in the list

#### Scenario: Deactivate a route

- **WHEN** a user with `delivery.manage` deactivates a route
- **THEN** the route's row reflects an inactive state

#### Scenario: Filter to active routes

- **WHEN** the user enables the active-only filter
- **THEN** only active routes are shown

### Requirement: Manage route drivers

The DeliveryView SHALL show, for a selected route, its assigned drivers (each by employee name) and
let an authorized user assign an employee as a driver and remove one; these mutations SHALL require
the `delivery.manage` permission. A duplicate assignment SHALL surface a friendly message rather
than a raw error.

#### Scenario: Assign a driver

- **WHEN** a user with `delivery.manage` assigns an employee to the route
- **THEN** the driver appears in the route's driver list

#### Scenario: Duplicate assignment is rejected friendly

- **WHEN** a user assigns an employee already assigned to that route
- **THEN** the screen shows a friendly "ese conductor ya está asignado" message and no duplicate is
  created

#### Scenario: Remove a driver

- **WHEN** a user with `delivery.manage` removes a driver from the route
- **THEN** the driver is no longer listed for the route

### Requirement: Permission gating and navigation

The Delivery screen SHALL be reachable at `/delivery` only for authenticated users with
`delivery.read`, exposed via a navigation entry; the route create/edit/deactivate and the driver
assign/remove controls SHALL be shown only with `delivery.manage`. This gating is UX — the backend
enforces authorization independently.

#### Scenario: Read-only delivery user

- **WHEN** the current user has `delivery.read` but not `delivery.manage`
- **THEN** the route list and drivers are visible read-only and no create, edit, deactivate, assign,
  or remove actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `delivery.read` navigates to `/delivery`
- **THEN** the router redirects them to the forbidden view
