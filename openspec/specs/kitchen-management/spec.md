# kitchen-management

## Purpose

Kitchen display system (KDS): kitchen stations per branch, product→station routing
configuration, sending an order's items to the line as tickets, and a station
board with a `pending → in_progress → ready` ticket lifecycle. Tenant/branch-
isolated and RBAC-protected.

Routing is also triggered automatically when an item is added to an order (handled by the
order-management item-add flow); the manual route endpoint remains for re-routing and fallback.

Out of scope for this capability: reflecting ticket readiness back into the order item's `orders`
status, and prep-time SLA metrics (the `entered_at`/`ready_at` timestamps are captured for a later
reporting change).
## Requirements
### Requirement: Tenant and branch isolation for kitchen

The system SHALL scope every kitchen read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate stations or tickets of another tenant.

#### Scenario: Tenant cannot see another tenant's stations
- **WHEN** a request for tenant A lists kitchen stations
- **THEN** only stations whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a station id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a kitchen endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage kitchen stations

The system SHALL allow authorized users to create, list, update and deactivate kitchen stations for a branch, each with a name, a display position, and an active flag.

#### Scenario: Create a station
- **WHEN** an authorized user creates a station for a branch of the current tenant
- **THEN** the station is persisted active and returned

#### Scenario: List stations for a branch
- **WHEN** an authorized user lists stations for a branch
- **THEN** only that branch's stations are returned, ordered by position

#### Scenario: Reject unknown branch
- **WHEN** a user creates a station for a `branch_id` not in the current tenant
- **THEN** the system responds 404 Not Found

### Requirement: Configure product-to-station routing

The system SHALL allow authorized users to map a product to one or more kitchen stations, remove a mapping, list a product's stations, and update an existing mapping's `role` and ordered task list (short task names, e.g. "Carne de hamburguesa", "Tocineta ahumada"; each ≤60 chars, at most 10 per mapping, empty by default). The product and station MUST belong to the current tenant; the same product-station pair MUST NOT be mapped twice.

#### Scenario: Attach a product to a station

- **WHEN** an authorized user maps an existing product to an existing station (optionally with a role and tasks)
- **THEN** the mapping is persisted

#### Scenario: Reject duplicate mapping

- **WHEN** a user maps a product to a station it is already mapped to
- **THEN** the system responds with a conflict error

#### Scenario: Update a mapping's role and tasks

- **WHEN** an authorized user updates an existing mapping with a new role and/or task list
- **THEN** the mapping reflects the new values without being detached and re-attached

#### Scenario: Oversized task list is rejected

- **WHEN** a mapping write carries more than 10 tasks or a task longer than 60 characters
- **THEN** the request fails validation and nothing is stored

#### Scenario: Detach a product from a station

- **WHEN** an authorized user removes an existing product-station mapping
- **THEN** the mapping no longer exists

### Requirement: Route an order to the kitchen

The system SHALL allow authorized users to route an order to the kitchen: for each non-cancelled order item, the system resolves the item's product (via its product variant) and creates a ticket (`order_item_stations`) in state `pending` for each station configured for that product, at the order's branch. Items whose product has no configured station SHALL produce no ticket. Routing SHALL be idempotent — an item already routed to a station SHALL NOT be duplicated — and this uniqueness SHALL be enforced by a database unique constraint on `(order_item_id, kitchen_station_id)` so concurrent routes converge instead of duplicating.

Routing an order whose payment method is anything other than cash SHALL be refused while its payment is unverified, so the kitchen never cooks a prepaid order whose money has not been confirmed. Cash orders SHALL route with no payment precondition — their money arrives at the door.

#### Scenario: Route creates tickets per configured station
- **WHEN** an authorized user routes an order whose item's product is mapped to a station
- **THEN** a `pending` ticket is created for that item at that station

#### Scenario: Item without a configured station produces no ticket
- **WHEN** an order item's product has no station mapping
- **THEN** routing creates no ticket for that item

#### Scenario: Cancelled items are not routed
- **WHEN** an order with a cancelled item is routed
- **THEN** no ticket is created for the cancelled item

#### Scenario: Routing is idempotent
- **WHEN** an order is routed twice
- **THEN** no duplicate tickets are created for an item-station already routed

#### Scenario: Concurrent routes cannot duplicate a ticket
- **WHEN** two route requests for the same order race each other
- **THEN** at most one ticket exists per (order item, station) afterwards, enforced by the
  database constraint, and both requests complete without error

#### Scenario: An unverified prepaid order is not routed
- **WHEN** a user routes an order whose payment method is `transfer` and whose payments do not cover its total
- **THEN** the system responds with a conflict error and no ticket is created

#### Scenario: A verified prepaid order routes normally
- **WHEN** an order whose payment method is `transfer` has been verified and is routed
- **THEN** its tickets are created as usual

#### Scenario: A cash order routes without payment
- **WHEN** a user routes an unpaid order whose payment method is `cash`
- **THEN** its tickets are created as usual

### Requirement: KDS board and ticket lifecycle

The KDS board SHALL list a station's tickets and advance them through their lifecycle. A
ticket read SHALL expose the ordering **note** captured on its order item (e.g. "sin
lechuga"), when present, so the cook sees any special instruction. The note is read-only
on the ticket (it belongs to the order item); all of an item's station tickets carry the
same note.

#### Scenario: Ticket exposes the item's note

- **WHEN** a station's tickets are listed and an item was ordered with a kitchen note
- **THEN** each of that item's tickets includes the note text

#### Scenario: No note is absent, not empty-shown

- **WHEN** an item has no kitchen note
- **THEN** its tickets report the note as absent (null)

### Requirement: RBAC protection of kitchen endpoints

The system SHALL require the `kitchen.read` permission for kitchen read endpoints (stations list, product routing list, station board) and the `kitchen.update` permission for writes (manage stations, configure routing, route an order, advance tickets).

#### Scenario: Read without permission
- **WHEN** a user lacking `kitchen.read` calls a kitchen read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Update without permission
- **WHEN** a user lacking `kitchen.update` tries to manage stations, route an order, or advance a ticket
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

### Requirement: Kitchen ticket change events

The system SHALL publish a kitchen event when a ticket is created by routing and when a ticket
is advanced, carrying at least the event type, branch id, station id, ticket id and resulting
status, on a channel scoped to the tenant and branch (Redis pub/sub). Publishing SHALL be
best-effort: a publish failure (e.g. Redis unavailable) SHALL NOT fail or delay the underlying
mutation.

#### Scenario: Advancing a ticket publishes an event

- **WHEN** an authorized user advances a ticket
- **THEN** a `ticket_advanced` event with the ticket's station, id and new status is published
  to the tenant/branch channel

#### Scenario: Routing publishes creation events

- **WHEN** routing an order creates tickets
- **THEN** a `ticket_created` event is published for the routed order's tickets on the
  tenant/branch channel

#### Scenario: Publish failure does not break the mutation

- **WHEN** the event broker is unreachable while a ticket is advanced
- **THEN** the advance succeeds and responds normally, and the failure is only logged

### Requirement: Kitchen events stream

The system SHALL expose a server-sent-events endpoint (`GET /kitchen/events`) that streams the
branch's kitchen events to authorized clients (`kitchen.read`), sending a heartbeat comment
periodically so intermediaries keep the connection open, and releasing the subscription when the
client disconnects. Tenancy SHALL be respected: a client only ever receives events of its own
tenant and requested branch.

#### Scenario: Board receives a ticket event

- **WHEN** a client with `kitchen.read` is connected to the events stream for a branch and a
  ticket on that branch is advanced
- **THEN** the client receives the `ticket_advanced` event on the open stream

#### Scenario: Stream is tenant and branch scoped

- **WHEN** a ticket changes in a different tenant or branch than the stream's
- **THEN** the connected client receives nothing for it

#### Scenario: Unauthorized stream is rejected

- **WHEN** a client without `kitchen.read` requests the events stream
- **THEN** the request is rejected with an authorization error

### Requirement: Station task lists frozen onto tickets

When routing creates a ticket, the system SHALL copy the mapping's task list onto the ticket
(alongside `role`), frozen at fire time: later edits to the mapping's tasks SHALL NOT alter
tickets already created. Tickets SHALL expose their tasks on the board API so kitchen screens
can render each station's itemized work for the dish.

#### Scenario: Routing copies tasks onto the ticket

- **WHEN** an order is routed and the item's product-station mapping has tasks configured
- **THEN** the created ticket carries that task list and the board API returns it

#### Scenario: Config edits do not rewrite fired tickets

- **WHEN** a mapping's tasks are edited after an order was routed
- **THEN** the existing ticket keeps the tasks captured at fire time; only subsequently routed
  orders carry the new list

#### Scenario: Mapping without tasks

- **WHEN** a mapping has no tasks configured
- **THEN** its tickets carry an empty task list and behave exactly as before this capability

### Requirement: Kitchen board scoped to the open cash session

The live kitchen board SHALL show only tickets whose order belongs to the branch's currently open cash session. Tickets whose order has no session or belongs to a closed session SHALL be excluded from the live board. Tickets inherit their session from their order.

#### Scenario: Only the open shift's tickets are shown

- **WHEN** the kitchen board is loaded for a branch with an open cash session
- **THEN** only tickets whose order belongs to that open session are shown

#### Scenario: Closed-session tickets drop off

- **WHEN** the cash session that an order was created under is closed
- **THEN** that order's kitchen tickets no longer appear on the live board

