## ADDED Requirements

### Requirement: Kitchen service layer

The Kitchen API service SHALL expose typed functions covering the `/kitchen` endpoints: list,
create and update stations; list, attach and detach product→station mappings; route an order
(`POST /kitchen/orders/{order_id}/route`); list a station's tickets
(`GET /kitchen/stations/{station_id}/tickets`, optional status filter); and advance a ticket
(`POST /kitchen/tickets/{ticket_id}/advance`).

#### Scenario: List a station's tickets

- **WHEN** `listTickets(stationId, status?)` is called
- **THEN** it GETs `/kitchen/stations/{stationId}/tickets` (passing `status_filter` when a status
  is given) and resolves with the array of `Ticket`

#### Scenario: Route an order to the kitchen

- **WHEN** `routeOrder(orderId)` is called
- **THEN** it POSTs to `/kitchen/orders/{orderId}/route` and resolves with the created tickets

#### Scenario: Advance a ticket

- **WHEN** `advanceTicket(ticketId)` is called
- **THEN** it POSTs to `/kitchen/tickets/{ticketId}/advance` and resolves with the updated ticket

### Requirement: Kitchen store with branch-scoped state

The Kitchen store SHALL hold the active branch's stations, product→station mappings, and the
tickets of the currently selected station, and SHALL load stations scoped to the active branch.
Mutations SHALL be write-through: after a successful call the store refetches the affected
collection so server state is shown verbatim.

#### Scenario: Load stations for the active branch

- **WHEN** the store loads stations for the active branch
- **THEN** `stations` holds that branch's stations and the board can select one

#### Scenario: Advancing a ticket refreshes the board

- **WHEN** `advanceTicket` succeeds for a ticket on the selected station
- **THEN** the store refetches that station's tickets so the ticket reflects its new status
  without a manual reload

#### Scenario: Routing an order refreshes the board

- **WHEN** an open order is routed to the kitchen
- **THEN** the store refetches the selected station's tickets so newly created tickets appear

### Requirement: Ticket label resolution

A ticket carries only `order_item_id`, so the store SHALL resolve a human label (product/variant
name and quantity) for each ticket from the available menu and order-item data, and SHALL degrade
gracefully to a short ticket reference when the item cannot be resolved.

#### Scenario: Resolvable ticket shows product label

- **WHEN** a ticket's `order_item_id` maps to a known order item and variant
- **THEN** the board shows the product/variant name and quantity for that ticket

#### Scenario: Unresolvable ticket degrades gracefully

- **WHEN** a ticket's `order_item_id` cannot be resolved to an item/variant
- **THEN** the board shows a short fallback reference instead of an empty or broken card

### Requirement: Cook-facing ticket board

The KitchenView SHALL present, for a selected station, that station's tickets grouped per order
into dockets, each showing the order's destination (table number or channel), an order reference,
the dishes with their quantities, and each dish's status. Advancing a ticket SHALL move it
strictly forward (`pending → in_progress → ready`); a ticket already `ready` SHALL NOT offer an
advance action. Dockets SHALL be ordered oldest-first, and fully-served dockets (all tickets
`ready`) SHALL be de-emphasised and sorted last.

#### Scenario: Tickets grouped per order

- **WHEN** a station with tickets from two different orders is selected
- **THEN** the board shows one docket per order, each listing that order's dishes (with quantity)
  and destination, and each dish carries its own status

#### Scenario: Advance moves a ticket forward

- **WHEN** the cook advances a `pending` ticket
- **THEN** the ticket moves to `in_progress`; advancing again moves it to `ready`

#### Scenario: Ready tickets are terminal

- **WHEN** a ticket is in `ready`
- **THEN** no advance action is offered for it and the dish reads as done

#### Scenario: Oldest orders surface first

- **WHEN** the board shows several dockets
- **THEN** unfinished dockets appear oldest-first and a docket whose tickets are all `ready` sinks
  below the unfinished ones

### Requirement: Elapsed-time aging

Each docket SHALL display how long its oldest ticket has been waiting and SHALL escalate its
visual urgency as that time grows (calm → warning → overdue), so a glance reveals what is running
late. The elapsed time SHALL update over time without a manual reload.

#### Scenario: Aging escalates with wait time

- **WHEN** a docket's oldest ticket has been waiting past the warning and overdue thresholds
- **THEN** the docket shows the elapsed time and escalates its urgency treatment accordingly

#### Scenario: Time updates live

- **WHEN** a docket remains on the board
- **THEN** its displayed elapsed time advances without the user reloading

### Requirement: Station rail with live backlog

The board SHALL present the branch's stations as a selectable rail, each station showing a live
count of its open (not-yet-`ready`) tickets, so the user can see where work is piling up and
switch stations directly.

#### Scenario: Rail shows open counts

- **WHEN** a station has unfinished tickets
- **THEN** the rail shows that station's open-ticket count and selecting it loads its board

### Requirement: Station and product mapping setup

The KitchenView SHALL let an authorized user create and edit stations (name, position, active
flag) and attach or detach products to a station; these setup controls SHALL be available only
with the `kitchen.update` permission.

#### Scenario: Create a station

- **WHEN** a user with `kitchen.update` creates a station with a name and position
- **THEN** the station is created and appears in the station list

#### Scenario: Map a product to a station

- **WHEN** a user with `kitchen.update` attaches a product to a station
- **THEN** the mapping is created so routing an order will send that product's items to the station

### Requirement: Route open orders from the kitchen

The KitchenView SHALL list the active branch's open orders and offer a "Enviar a cocina" action
that routes the order (`POST /kitchen/orders/{id}/route`); the action SHALL require the
`kitchen.update` permission and routing SHALL be safe to repeat (idempotent on the backend).

#### Scenario: Route an open order

- **WHEN** a user with `kitchen.update` chooses "Enviar a cocina" on an open order
- **THEN** the order's items are routed to their stations and the resulting tickets become
  visible on the relevant station boards

#### Scenario: Routing is repeatable without duplicates

- **WHEN** an order that was already routed is routed again
- **THEN** the action completes without creating duplicate tickets

### Requirement: Permission gating and navigation

The Kitchen screen SHALL be reachable at `/kitchen` only for authenticated users with
`kitchen.read`, exposed via a navigation entry; mutating controls (setup, routing, advance) SHALL
be shown only with `kitchen.update`. This gating is UX — the backend enforces authorization
independently.

#### Scenario: Read-only kitchen user

- **WHEN** the current user has `kitchen.read` but not `kitchen.update`
- **THEN** the board and setup are visible read-only and no advance/route/edit actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `kitchen.read` navigates to `/kitchen`
- **THEN** the router redirects them to the forbidden view
