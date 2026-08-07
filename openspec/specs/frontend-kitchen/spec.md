# frontend-kitchen

## Purpose

The Kitchen Display System (KDS) frontend — the cook-facing client for the backend `/kitchen`
module, scoped to the active branch. It lives on the dark "pass" (the heat-lamp field of the
login docket) because the screen is physically at the kitchen pass, not the office working
surface. The screen has three areas: the **pass** (the live board), **configuración** (station
setup and product→station mapping), and **ruteo** (sending open orders to the kitchen). On the
board each order is a paper docket — destination (table/channel), order reference, dishes with
quantities, per-dish status, and an elapsed-time timer that warms (calm → warning → overdue) as
the order waits, so lateness is visible at a glance. A station rail shows each station's open
backlog. A ticket carries only `order_item_id`, so dish labels are resolved client-side from the
menu and open orders, degrading to a short reference when unresolvable. Order totals and ticket
state are always the server's; the screen only derives presentation (labels, grouping, aging).
The screen is reached with `kitchen.read` and mutating controls (setup, routing, advance) are
gated by `kitchen.update`; this gating is UX — the backend enforces authorization independently.
Realtime push, recall/un-advance, SLA metrics, and printing are out of scope for this slice.
## Requirements
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
tickets of **all active stations** (loaded per station and merged), so the board can present the
whole kitchen at once and filter by station client-side. Mutations SHALL be write-through: after
a successful call the store refetches the affected tickets so server state is shown verbatim.

#### Scenario: Load stations for the active branch

- **WHEN** the store loads stations for the active branch
- **THEN** `stations` holds that branch's stations and the board can select one

#### Scenario: Load the whole board

- **WHEN** the store loads tickets for the board
- **THEN** it fetches each active station's tickets and exposes the merged set, keyed so the
  board can group by order and filter by station

#### Scenario: Advancing a ticket refreshes the board

- **WHEN** `advanceTicket` succeeds for a ticket on the board
- **THEN** the store refetches tickets so the ticket reflects its new status without a manual
  reload

#### Scenario: Routing an order refreshes the board

- **WHEN** an open order is routed to the kitchen
- **THEN** the store refetches tickets so newly created tickets appear

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

The cook-facing board SHALL render each ticket for a station and, when the item was
ordered with a kitchen **note** (e.g. "sin lechuga"), SHALL display that note prominently
on the item row so the cook cannot miss it and does not prepare something that was not
ordered. The note is shown as plain text.

#### Scenario: Ticket shows the ordering note

- **WHEN** a ticket's item carries a kitchen note
- **THEN** the note is rendered prominently on that item row (e.g. "⚠ SIN LECHUGA")

#### Scenario: No note, no clutter

- **WHEN** a ticket's item has no note
- **THEN** no note element is rendered for it

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

The board SHALL present the branch's active stations as a filter rail driven by the stations in
the database (no hardcoded station set). Each station SHALL show a stable two-letter tag derived
from its name (deterministically uniquified on collision), its name, and a live count of its open
(not-yet-`ready`) tickets. Selecting a station SHALL filter the board to dockets containing that
station's work; a "all stations" selection SHALL show everything.

#### Scenario: Rail reflects DB stations

- **WHEN** the active branch has stations configured in the database
- **THEN** the rail lists exactly those active stations, each with a two-letter tag and name

#### Scenario: Rail shows open counts and filters

- **WHEN** a station has unfinished tickets and the user selects it in the rail
- **THEN** the rail shows that station's open-ticket count and the board filters to dockets with
  work for that station

### Requirement: Station and product mapping setup

The KitchenView SHALL let an authorized user create and edit stations (name, position, active
flag), attach or detach products to a station, and edit an existing mapping's role and task list
(the itemized names shown on the board's components) without detaching; these setup controls
SHALL be available only with the `kitchen.update` permission.

#### Scenario: Create a station

- **WHEN** a user with `kitchen.update` creates a station with a name and position
- **THEN** the station is created and appears in the station list

#### Scenario: Map a product to a station

- **WHEN** a user with `kitchen.update` attaches a product to a station
- **THEN** the mapping is created so routing an order will send that product's items to the station

#### Scenario: Edit a mapping's tasks

- **WHEN** a user with `kitchen.update` edits a mapping's task list (add, remove, rename)
- **THEN** the mapping is updated in place and newly routed orders carry the new tasks

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

### Requirement: Automatic board refresh

The board SHALL refresh automatically. While a kitchen events stream (SSE) is connected, ticket
events SHALL drive refreshes (debounced) and polling SHALL relax to a slow fallback cadence;
when the stream is unavailable or errors, the board SHALL fall back to polling (~10 s) and keep
retrying the stream with backoff. Polling SHALL skip a tick if the previous fetch is still in
flight, SHALL keep showing the last good data when a fetch fails, and SHALL stop when the board
is unmounted. The stream client SHALL authenticate with the Bearer token (fetch-stream, not bare
EventSource). A manual refresh affordance SHALL remain available.

#### Scenario: Ticket change arrives via the stream

- **WHEN** the stream is connected and a ticket is advanced elsewhere
- **THEN** the board reflects the change within ~1–2 s without waiting for a polling tick

#### Scenario: Stream down degrades to polling

- **WHEN** the events stream cannot connect or drops
- **THEN** the board continues refreshing via ~10 s polling and periodically retries the stream

#### Scenario: Failed fetch degrades gracefully

- **WHEN** a refresh fetch fails
- **THEN** the board keeps the previously loaded tickets and retries on the next tick

### Requirement: Order readiness rollup and bump

The board SHALL derive an order-level readiness state from the order's tickets — an order is
ready when all its tickets are `ready` — and reflect it on the docket. A docket SHALL offer a
bump action (gated by `kitchen.update`) that advances all of the order's remaining tickets to
`ready` using the existing advance endpoint; the action SHALL be disabled while in flight and the
board SHALL show the server's resulting state afterwards.

#### Scenario: Rollup derived from tickets

- **WHEN** the last unfinished ticket of an order reaches `ready`
- **THEN** the docket reads as ready and moves out of the default board into the "Listas"
  toggle (per board ordering and the ready filter)

#### Scenario: Bump completes an order

- **WHEN** a user with `kitchen.update` bumps a docket with `pending` and `in_progress` tickets
- **THEN** each remaining ticket is advanced to `ready` and the refreshed board shows the order
  fully ready

#### Scenario: Partial bump failure shows server truth

- **WHEN** a bump fails after advancing only some tickets
- **THEN** the board refetches and shows exactly the statuses the server holds, with no stuck
  optimistic state

### Requirement: My-station mode

The board SHALL offer a single-station list mode ("my station") that shows only the selected
station's unfinished work as a dense, oldest-first list optimized for a cook at one station, with
the same tap-to-advance behavior as the docket view.

#### Scenario: Cook works a single station

- **WHEN** the user enters my-station mode for a selected station
- **THEN** only that station's unfinished tickets are listed oldest-first and tapping one
  advances it forward

### Requirement: Expo alert panel

The board SHALL offer an expo panel that lists orders sorted by severity (most overdue first),
showing for each order its waiting time, alert severity, and which stations still owe work, so an
expeditor can see at a glance what is blocking the pass.

#### Scenario: Expeditor sees blocking stations

- **WHEN** an order has some dishes ready and one station's dish still `pending` past its
  warning threshold
- **THEN** the expo panel lists the order with its severity and names the station still owing
  work

### Requirement: Recipe drawer on real data

The board SHALL offer a recipe affordance per dish that opens a drawer showing the dish's
recipe card fetched from the backend (`/recipes` card endpoint): ingredients with quantity and
unit, preparation steps, and allergens. The drawer SHALL show a loading state while fetching,
SHALL degrade gracefully when the variant has no recipe (a quiet "no recipe" note, no error
noise), and SHALL never show mock recipe content in production.

#### Scenario: Cook opens a dish's recipe

- **WHEN** the cook taps the recipe affordance of a dish whose variant has a recipe card
- **THEN** the drawer shows its ingredients, steps and allergens from the backend

#### Scenario: Dish without a recipe

- **WHEN** the recipe card responds not-found
- **THEN** the drawer communicates there is no recipe for the dish, without an error state

### Requirement: A table ticket says its table, its diner and that nobody vetted it

A kitchen ticket for a `dine_in` order SHALL show its table number, and its diner name when the
order carries one. A ticket whose order has `origin` `qr` SHALL additionally carry a mark saying so.

The table and the name are what the food is delivered by: without a waiter, whoever carries the
plate out has only the ticket to know where it goes and whose it is. The `qr` mark is a different
statement — it says no member of staff looked at this order before it reached the stove, which is
the one thing a cook should know about it and cannot infer from anything else on the ticket.

The mark SHALL follow the board's existing mono treatment for tags. Colour on this board is reserved
for heat and state, and an order's provenance is neither.

#### Scenario: A table ticket carries where and whose
- **WHEN** a ticket belongs to a `dine_in` order on table 5 placed by "Ana"
- **THEN** the ticket shows table 5 and "Ana"

#### Scenario: A QR ticket is marked
- **WHEN** a ticket belongs to an order with `origin` `qr`
- **THEN** it carries a mark identifying it as self-ordered, rendered as a mono tag

#### Scenario: A waiter's ticket is not marked
- **WHEN** a ticket belongs to a `dine_in` order opened by staff
- **THEN** it shows the table but carries no self-ordered mark

#### Scenario: Rounds read as separate tickets
- **WHEN** a diner's second round is routed
- **THEN** it appears as its own ticket, aged from its own routing time, alongside the first

