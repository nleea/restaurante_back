# frontend-delivery (delta)

## MODIFIED Requirements

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

## ADDED Requirements

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
