# frontend-delivery

## Purpose

The delivery route-configuration frontend — the client for the route slice of the backend
`/delivery` (own-fleet) module, living on the light office working surface. Routes are branch-scoped,
so the screen uses the active-branch context (the list filters by `branch_id` and create sends it).
It is a master–detail screen: a route **list** (master) with an active filter, and a per-route
**detail** holding the name and covered zones with an edit form and a deactivate/reactivate action,
plus the route's **drivers** — each row showing the assigned employee's name, with assign (pick an
employee) and remove controls. Because the backend exposes no route DELETE, deactivation is a PATCH
that flips `is_active`; the PATCH also edits name and `covered_zones` (a plain free-text string),
so the detail offers a real edit form. Route drivers carry only `employee_id`, so names are resolved
from the staff directory the other screens use, and the assign picker offers the active branch's
employees, excluding those already assigned to avoid the duplicate-assign conflict. The screen is
reached with `delivery.read`; the route create/edit/deactivate and the driver assign/remove controls
are gated by `delivery.manage` — UX gating only, the backend enforces authorization independently.
Per-order delivery records, dispatch runs, and the assign→depart→deliver/finish lifecycle (which use
the separate `delivery.assign` permission), plus cash-on-delivery, auto-assignment/optimization, live
GPS, and order-status reflection, are out of scope for this slice (a follow-up
`frontend-delivery-dispatch` change).
## Requirements
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

The delivery screen at `/delivery` SHALL present the branch's routes as a list synced to a
coverage ring map: each route shows its name, zone names, ring color and assigned-driver count,
with an active-only filter. An authorized user SHALL be able to create a route (name, zones as
chips, color from preset swatches — previewed as a dashed ring on the map before saving), edit
those fields, and deactivate or reactivate it; these mutations SHALL require the
`delivery.manage` permission and write through to the API so the screen shows server state.

#### Scenario: Create a route

- **WHEN** a user with `delivery.manage` submits the new-route form with a name
- **THEN** the route is created via the API, appears in the list, and its ring appears on the map
  at the next band

#### Scenario: Deactivate a route

- **WHEN** a user with `delivery.manage` deactivates a route
- **THEN** the route reads inactive in the list, its ring leaves the map, and the remaining
  active rings compact their bands inward

#### Scenario: Filter to active routes

- **WHEN** the user enables the active-only filter
- **THEN** only active routes are shown in the list and on the map

### Requirement: Manage route drivers

The delivery screen SHALL show, for a selected route, its assigned drivers (each by employee
name) with their derived status pill (`En ruta` / `Disponible` / `Inactivo` from the API's
status), and let an authorized user assign an employee as a driver (searchable modal over the
not-yet-assigned pool) and remove one with an inline two-tap confirm; these mutations SHALL
require the `delivery.manage` permission. A duplicate assignment SHALL surface a friendly
message rather than a raw error.

#### Scenario: Assign a driver

- **WHEN** a user with `delivery.manage` assigns an employee to the route
- **THEN** the driver appears in the route's driver list with a status pill

#### Scenario: Duplicate assignment is rejected friendly

- **WHEN** a user assigns an employee already assigned to that route
- **THEN** the screen shows a friendly "ese conductor ya está asignado" message and no duplicate
  is created

#### Scenario: Remove a driver

- **WHEN** a user with `delivery.manage` removes a driver from the route
- **THEN** the driver is no longer listed for the route

#### Scenario: Status pills reflect dispatch

- **WHEN** an assigned driver has a run in progress
- **THEN** their pill reads "En ruta" without this screen writing any state

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

### Requirement: Coverage ring map

The delivery screen SHALL render an interactive map centered on the branch's business location
with one ring per **active** route: consecutive bands of the branch's `ring_step_km`, assigned
by the active routes' order (band positions compact among active routes — a lone active route
rings the innermost band), stroked and filled in each route's color. Inactive routes SHALL have
no ring and SHALL NOT occupy a band. Selecting a route (from the list, the map, or the radius
panel) SHALL highlight its ring, dim the others, frame it in view, and open the route's detail.
The rings SHALL NOT render before a business location exists.

#### Scenario: Rings mirror the active routes

- **WHEN** the branch has active routes and a business location
- **THEN** the map shows one ring per active route at its compacted band, in its color, and
  clicking a ring selects that route

#### Scenario: Bands compact among active routes

- **WHEN** every route but one is deactivated and the step is 0.5 km
- **THEN** the remaining route rings the innermost band (up to 0.5 km), not its old position's
  distance

#### Scenario: Selection highlights

- **WHEN** a route is selected
- **THEN** its ring emphasizes, the others dim, and the view frames the selected ring

### Requirement: Business location onboarding

When the branch has no business coordinates, the screen SHALL guide the user to set them: it MAY
ask the device's location once as a centering suggestion (denial does not block), and the next
map click SHALL place the business pin, persisted on confirmation (`delivery.manage`); rings
appear once saved. The location SHALL be relocatable later through the same pick-on-map flow.

#### Scenario: First-run pin placement

- **WHEN** a user with `delivery.manage` opens the screen for a branch without coordinates,
  clicks the map and confirms
- **THEN** the coordinates persist and the rings render around the new pin

#### Scenario: Geolocation denied

- **WHEN** the device location permission is denied
- **THEN** onboarding continues — the map simply stays at its default view until the user clicks

#### Scenario: Relocate later

- **WHEN** an authorized user chooses to relocate the business and clicks a new point
- **THEN** the saved coordinates update and every ring re-centers

### Requirement: Ring radius configuration

The screen SHALL offer a radius panel showing each route's computed band (color, code, range in
km) with a live miniature of the rings, and a slider + numeric input for the branch's
`ring_step_km` (0.5–5.0). Moving the control SHALL redraw the map immediately and persist the
value (debounced) with `delivery.manage`; every band recomputes from the single step.

#### Scenario: Step change persists

- **WHEN** a user with `delivery.manage` settles the slider on a new step
- **THEN** all rings redraw at the new bands and the value is saved so a reload shows the same
  rings

### Requirement: Live deliveries overlay

The deliveries overlay SHALL paint each order's pin from its stored `latitude`/`longitude`.
Those coordinates are geocoded server-side from the address (the frontend does not
geocode). When an order has no pin (geocoding did not resolve its address), the overlay
SHALL make it clear the location is unset and SHALL let an operator place it with the manual
map picker; an approximate pin MAY be dragged to correct it. A manually placed pin is
authoritative and is not re-derived by geocoding.

#### Scenario: A geocoded order is painted on the map

- **WHEN** a delivery order has server-derived coordinates
- **THEN** its pin is painted at that approximate location on the map

#### Scenario: An order without a pin can be placed manually

- **WHEN** a delivery order has no coordinates
- **THEN** the overlay surfaces that its location is unset and the operator can place it with
  the manual picker

#### Scenario: Correcting an approximate pin

- **WHEN** an operator adjusts an order's pin with the manual picker
- **THEN** the corrected location is saved and treated as authoritative

### Requirement: Live driver layer on the coverage map

The coverage map SHALL render a live driver layer so the dispatcher can see the domiciliario: for each active run, the driver's current-position marker (distinct from delivery drops and the branch pin, labeled with the driver's name) and their recorded trail as a polyline. Each driver marker SHALL show how fresh its position is (e.g. "hace X min"); positions older than a staleness threshold SHALL be visually de-emphasized rather than shown as if live. The layer SHALL refresh on an interval (or via realtime push) and SHALL show only active runs.

#### Scenario: Active driver appears on the coverage map
- **WHEN** a driver is tracking during an active run and the dispatcher views the coverage map
- **THEN** the map shows that driver's current-position marker and trail, labeled with the driver's name

#### Scenario: Staleness is shown
- **WHEN** a driver's latest position is several minutes old
- **THEN** the marker shows its age and is de-emphasized rather than presented as current

#### Scenario: Finished runs leave the layer
- **WHEN** a run finishes
- **THEN** its driver marker and trail are removed from the live layer on the next refresh

#### Scenario: The layer refreshes
- **WHEN** a tracked driver moves and time passes
- **THEN** the dispatcher's map updates the driver's marker and extends the trail without a manual reload

### Requirement: Manage kilometer delivery tariffs

The delivery administration screen SHALL let a user with `delivery.manage` create, edit and view the active branch's ordered kilometer tariff bands and their fees. It SHALL show the maximum covered distance and prevent saving invalid band arrangements; users without that permission see the configured plan without write controls.

#### Scenario: Manager changes a band fee
- **WHEN** a manager changes the fee for the band ending at 4 km and saves a valid plan
- **THEN** future quotes use that fee while already quoted orders retain their prior fee

#### Scenario: Read-only delivery user sees pricing
- **WHEN** a user has `delivery.read` but not `delivery.manage`
- **THEN** they can see the active kilometer bands but cannot modify them

### Requirement: Surface quote and payment-request operations

The dispatch surface SHALL show each delivery's quote status, adjusted distance and frozen fee when available, plus whether its payment request was sent, failed or needs operational follow-up.

#### Scenario: Dispatcher sees an unquoted delivery
- **WHEN** a delivery awaits geocoding or distance calculation
- **THEN** its row clearly states that it is pending quote instead of showing a zero fee as final

#### Scenario: Dispatcher sees a failed message emission
- **WHEN** a quoted delivery's WhatsApp payment-request emission fails
- **THEN** its row identifies the failure and offers the authorized operational retry/follow-up

