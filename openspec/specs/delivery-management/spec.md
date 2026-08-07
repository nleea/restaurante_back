# delivery-management

## Purpose

Own-fleet delivery (no external apps): delivery routes per branch, route drivers,
per-order delivery records with explicit states, and dispatch runs with an
assign → depart → deliver → finish lifecycle. Tenant/branch-isolated and
RBAC-protected.

Resolving a delivery settles its order — cash collected at the door, and the order
closed either way. The rules for that live in `delivery-settlement`; this capability
owns the delivery's own lifecycle and the gate that keeps uncooked food off a run.

Out of scope for this capability: auto-assignment by zone / route optimization, and
live GPS tracking.
## Requirements
### Requirement: Tenant and branch isolation for delivery

The system SHALL scope every delivery read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate routes, runs or deliveries of another tenant.

Delivery records, dispatch runs and route drivers SHALL each carry a `branch_id`, like the routes and branch settings they belong with, so the operational records of one branch are separable from another's.

That `branch_id` SHALL be **derived by the system, never accepted from the request**: a delivery record takes the branch of its order; a run and a route driver take the branch of their route. No create or update request SHALL carry a `branch_id` for these records.

Listing delivery records and listing runs SHALL require a `branch_id` and SHALL return only the records of that branch. It SHALL NOT be possible to list every delivery record or run of a tenant across branches.

#### Scenario: Tenant cannot see another tenant's routes
- **WHEN** a request for tenant A lists delivery routes
- **THEN** only routes whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a route id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a delivery endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

#### Scenario: A delivery record takes its order's branch
- **WHEN** a delivery record is created for an order of branch A
- **THEN** the delivery record's branch is A, without the request naming it

#### Scenario: A run and a route driver take their route's branch
- **WHEN** a run is created for a route of branch A, or a driver is attached to that route
- **THEN** the run and the route driver carry branch A, without the request naming it

#### Scenario: Listing is scoped to one branch
- **WHEN** delivery records or runs are listed for branch A of a tenant that also operates branch B
- **THEN** only branch A's records are returned, and branch B's are absent

#### Scenario: Listing without a branch is rejected
- **WHEN** delivery records or runs are listed with no branch given
- **THEN** the system rejects the request rather than returning the tenant's records across branches

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

### Requirement: Create a per-order delivery record

The system SHALL create a per-order delivery record from an order, its address text, and an
optional neighborhood and pin. Creating the record SHALL NOT wait on a geocoding provider:
when **no explicit pin** is provided, the record SHALL be stored with an unset location, and
its pin SHALL be resolved afterwards in the background (see the `delivery-geocoding-worker`
capability) or placed by hand. An explicitly provided pin SHALL always be kept as-is and never
overwritten.

#### Scenario: Create with only an address stores no pin

- **WHEN** a delivery record is created with an address but no pin
- **THEN** the record is created immediately with an unset latitude/longitude, left for
  background resolution

#### Scenario: An explicit pin is preserved

- **WHEN** a delivery record is created with an explicit pin
- **THEN** that pin is stored unchanged and nothing overwrites it

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

The system SHALL support an explicit delivery lifecycle. Assigning a delivery to a `preparing` run sets the delivery's route and run and moves it to `assigned`. Departing a run moves it `preparing → in_transit` (stamping `departed_at`) and moves its `assigned` deliveries to `in_transit`. A delivery SHALL be markable `delivered` only from `in_transit`, and markable `not_delivered` from **any non-terminal state** (`pending`, `assigned` or `in_transit`), stamping `delivered_at`; marking `not_delivered` SHALL accept and persist an optional reason (from a fixed list) and an optional free-text comment. A delivery SHALL additionally become `cancelled` when its order is cancelled and it never left the store (see below). Finishing a run moves it `in_transit → finished`. Backward transitions and transitions out of a terminal state (`delivered`, `not_delivered`, `cancelled`) SHALL be rejected.

Allowing `not_delivered` from any non-terminal state is what guarantees every delivery can reach an ending: an order that was cooked and never left would otherwise be unresolvable, and would block its shift's cash session forever.

`cancelled` is a THIRD terminal state and not a flavour of `not_delivered`, because `not_delivered` feeds the delivery-failure figures the operation reads. A cancelled order never left the store, so counting it as a failed delivery would invent a failure that did not happen.

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

#### Scenario: Reject marking delivered before departure
- **WHEN** a user marks a `pending` or `assigned` delivery as delivered
- **THEN** the system responds with a conflict error

#### Scenario: Mark a delivery not delivered with a reason
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered with a reason and optional comment
- **THEN** its status becomes `not_delivered` with `delivered_at` set and the reason (and comment, if any) persisted

#### Scenario: Mark a delivery not delivered without a reason
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered without a reason
- **THEN** its status becomes `not_delivered` with `delivered_at` set and no reason recorded

#### Scenario: Resolve an order that never left the store
- **WHEN** an authorized user marks a `pending` or `assigned` delivery as not delivered with a reason
- **THEN** its status becomes `not_delivered` with `delivered_at` set and the reason persisted

#### Scenario: Reject re-resolving a terminal delivery
- **WHEN** a user marks a `delivered`, `not_delivered` or `cancelled` delivery again
- **THEN** the system responds with a conflict error

#### Scenario: A cancelled delivery is not counted as a failed delivery
- **WHEN** delivery-failure figures are read for a period containing a `cancelled` delivery
- **THEN** that delivery is not among the failed ones

#### Scenario: Finish a run
- **WHEN** an authorized user finishes an `in_transit` run
- **THEN** the run becomes `finished` with `finished_at` set

#### Scenario: Reject finishing a non-in-transit run
- **WHEN** a user finishes a run that is not `in_transit`
- **THEN** the system responds with a conflict error

### Requirement: Every consumer of "resolved" reads the same list of terminal states

The set of terminal delivery states SHALL have a single definition, and every place that asks
whether a delivery is resolved SHALL derive its answer from it — the cash-session close guard, the
pending summary and the session history included.

Copying the list is what makes this dangerous: a state added in one place and missed in another
leaves the block in place with no visible cause, and the symptom is identical to the bug it was
meant to fix.

#### Scenario: A new terminal state reaches every consumer at once
- **WHEN** a terminal delivery state is added to the system
- **THEN** the close guard, the pending summary and the session history all treat it as resolved
  without any of them being changed separately

#### Scenario: A delivery in a terminal state never blocks its shift
- **WHEN** a session's only delivery is in any terminal state
- **THEN** the session can be closed

### Requirement: A delivery is assignable only once its order is cooked

A delivery SHALL be assignable to a run only when its order's kitchen readiness is `ready`.
Assigning a delivery whose order has not finished in the kitchen SHALL be rejected as a conflict,
stating that the order is not ready. This SHALL apply regardless of payment method: the payment
method decides when the money arrives, never when the food leaves.

Readiness SHALL be derived from the order rather than stored on the delivery, so the two can
never disagree.

#### Scenario: Assigning a cooked order succeeds

- **WHEN** an authorized user assigns a `pending` delivery whose order is `ready` to a
  `preparing` run
- **THEN** the assignment succeeds

#### Scenario: Assigning an order still in the kitchen is refused

- **WHEN** a user assigns a delivery whose order is `in_kitchen` to a run
- **THEN** the system responds with a conflict error stating the order is not ready
- **AND** the delivery keeps its previous status and run

#### Scenario: Assigning an order that never reached the kitchen is refused

- **WHEN** a user assigns a delivery whose order has no kitchen tickets at all
- **THEN** the system responds with a conflict error

#### Scenario: A cash order is held to the same rule

- **WHEN** a user assigns a delivery of a cash order that is `in_kitchen`
- **THEN** the system responds with a conflict error

### Requirement: Deliveries report why they cannot be assigned

The delivery listing SHALL report each delivery's kitchen readiness, so a delivery that cannot yet
be assigned can be shown as blocked with its reason rather than hidden or silently rejected.

#### Scenario: Readiness travels with the listing

- **WHEN** deliveries are listed for a branch
- **THEN** each carries its order's kitchen readiness

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

### Requirement: Delivery record timestamps and notes

The system SHALL persist `created_at` and `updated_at` timestamps on per-order delivery records and
SHALL expose `created_at` on the delivery read model and on the dispatch-run read model. Delivery
records SHALL support an optional free-text `notes` field (≤ 500 characters), editable through the
existing delivery update endpoint under the `delivery.manage` permission.

#### Scenario: Delivery exposes its creation time

- **WHEN** an authorized user creates a delivery and then reads it
- **THEN** the response includes a `created_at` timestamp set at creation time

#### Scenario: Run exposes its creation time

- **WHEN** an authorized user reads a dispatch run
- **THEN** the response includes the run's `created_at` timestamp

#### Scenario: Update delivery notes

- **WHEN** a user with `delivery.manage` patches a delivery with `notes`
- **THEN** the notes are persisted and returned on subsequent reads

#### Scenario: Overlong notes are rejected

- **WHEN** a user patches a delivery with notes longer than 500 characters
- **THEN** the system responds with a validation error and the delivery is unchanged

### Requirement: Geocode a delivery address to an approximate pin

The system SHALL provide a geocoder that turns a delivery's written address into an
approximate map location (latitude/longitude) plus, when available, its neighborhood. The
geocoder SHALL be biased to the branch's business location (the delivery-settings pin) and
constrained to the country, so a street resolves within the business's city. Geocoding is
**best-effort**: a failure or no-match SHALL leave the location unset and MUST NOT fail the
operation. The geocoder providers SHALL be configurable behind a stable interface, so they can
be replaced (e.g. self-hosted) without changing callers. Results SHOULD be cached so a repeated
address does not re-query the provider.

Addresses arrive in Colombian nomenclature (`Calle 41A #12C-48`), which names **two** streets —
the street and the cross street — whose crossing is the address's corner. The house number
names no mapped feature. The geocoder SHALL therefore derive both streets from the address and
resolve **their intersection**, while the address SHALL be stored verbatim — the house number
is what the driver delivers by. An address the geocoder cannot parse SHALL be queried as
written rather than rejected.

When the intersection cannot be resolved — either street missing from the map data, or an
address naming only one street — the geocoder SHALL fall back to resolving the street alone.
A street-only pin SHALL be understood as accurate only to the street: map data splits a street
into many segments and a single-point query answers with an arbitrary one, so the error is
bounded by the street's length. Measured in Riohacha: a street-only pin landed **27 m** from
the wrong corner (`Carrera 10`) for an address on `Carrera 12C` **555 m** away, and **3995 m**
from the true corner for another address. The intersection is therefore preferred wherever it
resolves, and consumers that reason about distance — ring assignment above all — SHALL treat a
street-only pin as no better than street-accurate.

The geocoder SHALL **verify** every street match: a result whose road does not name the street
that was asked for SHALL be treated as no match. When a street carries a letter suffix that
yields no match, the geocoder SHALL retry with the base street (`Calle 41A` → `Calle 41`), for
the intersection as well as for the street-only fallback. It SHALL NOT resolve to the cross
street alone: that street's own point bears no defined relation to the address and has been
measured a full ring band away.

An address with no verified match SHALL yield no location, to be placed by hand.

Geocoding SHALL NOT run inside creating or updating a delivery record: those operations SHALL
store the address and return, leaving the pin to be resolved afterwards (see the
`delivery-geocoding-worker` capability). Editing an address without giving an explicit pin
SHALL clear the stored pin, so the record is resolved again from its new address. An explicitly
provided pin SHALL always be preserved and never re-derived.

#### Scenario: The address's corner is resolved

- **WHEN** an address naming a street and a cross street both present in the map data is
  geocoded
- **THEN** the location returned is their intersection, not a point on either street

#### Scenario: A letter-suffixed street still finds its corner

- **WHEN** `Calle 41A #12C-48` is geocoded and the map data holds `Calle 41` but not `Calle 41A`
- **THEN** the intersection of `Calle 41` and `Carrera 12C` is returned

#### Scenario: No resolvable intersection falls back to the street

- **WHEN** the intersection of the two streets cannot be resolved
- **THEN** the street alone is resolved and returned, and the pin is understood as
  street-accurate only

#### Scenario: The house number does not prevent a resolution

- **WHEN** an address in Colombian nomenclature such as `Calle 15 #10-20` is geocoded
- **THEN** the streets are queried without the house number, and the stored address keeps the
  house number unchanged

#### Scenario: A match on a different road is rejected

- **WHEN** the provider answers a request for one street with a result whose road is another
  street
- **THEN** the geocoder treats it as no match and returns no location

#### Scenario: The cross street is never resolved on its own

- **WHEN** no intersection and no street verifies for `Calle 41A #12C-48`
- **THEN** the geocoder returns no location, and does not resolve to Carrera 12C

#### Scenario: An unparseable address is still attempted

- **WHEN** an address does not match the nomenclature the parser knows
- **THEN** it is queried as written, and geocoding neither raises nor blocks the operation

#### Scenario: Creating a delivery does not wait for a pin

- **WHEN** a delivery record is created with an address
- **THEN** the record is stored immediately with no location, and the caller is not blocked by
  any geocoding provider

#### Scenario: Editing an address queues it for re-resolution

- **WHEN** a delivery's address is edited and no explicit pin is provided
- **THEN** the stored pin is cleared so the record is resolved again from the new address

#### Scenario: An explicit pin is preserved

- **WHEN** a delivery carries an explicitly provided pin
- **THEN** that pin is kept as-is and is never re-derived from the address

#### Scenario: An unresolvable address yields no location

- **WHEN** the address cannot be matched
- **THEN** the geocoder returns no location and the caller proceeds with an unset pin

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

### Requirement: Delivery changes publish realtime events

Delivery and run mutations SHALL publish a best-effort `delivery` realtime event scoped to the branch, so live views (dispatch board, coverage map, driver) can refresh. This SHALL include: creating a delivery, assigning it, departing a run, marking a delivery delivered/not-delivered, finishing a run, a driver self-opening a run, and the **geocoding worker resolving a delivery's pin** (a separate process, whose change would otherwise be invisible to open screens). Publishing SHALL be best-effort and SHALL NOT fail the mutation if the broker is down.

#### Scenario: Creating a delivery notifies the branch
- **WHEN** a delivery is created for a branch
- **THEN** a `delivery` event for that branch is published

#### Scenario: A lifecycle transition notifies the branch
- **WHEN** a delivery is assigned, departed, marked, or a run is finished
- **THEN** a `delivery` event for that branch is published

#### Scenario: The geocoding worker's pin resolution notifies the branch
- **WHEN** the background geocoding worker resolves a delivery's location
- **THEN** a `delivery` event for that branch is published, so an open map updates

#### Scenario: A broker outage does not block the mutation
- **WHEN** the broker is unavailable during a delivery mutation
- **THEN** the mutation succeeds and no event is delivered

### Requirement: Delivery events stream

The system SHALL expose the branch's `delivery` events as an SSE stream under `delivery.read`, so a browser can subscribe and refetch on change.

#### Scenario: A dispatcher streams delivery events
- **WHEN** a client holding `delivery.read` opens the delivery events stream for a branch
- **THEN** it receives that branch's delivery events

#### Scenario: Streaming without permission is rejected
- **WHEN** a client lacking `delivery.read` opens the delivery events stream
- **THEN** the request is rejected

### Requirement: Deliveries listing scoped to the open cash session

The live deliveries listing (the dispatch board's source) SHALL return only deliveries whose order belongs to the branch's currently open cash session. Deliveries whose order has no session (`cash_session_id` null) or belongs to a closed session SHALL be excluded from the live list. Deliveries inherit their session from their order; they do not carry their own `cash_session_id`.

#### Scenario: Only the open shift's deliveries are listed

- **WHEN** the deliveries list is requested for a branch with an open cash session
- **THEN** only deliveries whose order belongs to that open session are returned

#### Scenario: Old deliveries are excluded

- **WHEN** a delivery's order belongs to a closed session or has no session
- **THEN** that delivery does not appear in the live deliveries list

#### Scenario: No open session yields an empty live list

- **WHEN** the deliveries list is requested for a branch with no open cash session
- **THEN** the live list is empty

### Requirement: Delivery location changes coordinate with quoting

The delivery module SHALL expose the quote status of each delivery and SHALL notify the quote workflow when a delivery record gains coordinates or when its address or coordinates change. An explicit or hand-placed pin remains authoritative for location; quote calculation consumes it but does not overwrite it.

#### Scenario: Background geocoding makes a delivery quotable

- **WHEN** the geocoding worker persists coordinates for a pending delivery
- **THEN** the delivery becomes eligible for asynchronous distance quotation

#### Scenario: Manual pin replaces an unresolved address

- **WHEN** an operator places a pin for a delivery whose address could not be resolved
- **THEN** the pin is retained as the delivery location and a quote can be calculated from it

