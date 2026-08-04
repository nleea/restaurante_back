# frontend-kitchen (delta)

## MODIFIED Requirements

### Requirement: Cook-facing ticket board

The KitchenView SHALL present the board as KDS order dockets: each order's tickets grouped into
one docket showing the destination (table number or channel) and an order reference. Within a
docket, tickets SHALL be grouped by order item: one dish row per order item (label and quantity
from the store's resolution, degrading to a short ticket reference when unresolvable), with one
tappable component per ticket. A component's name SHALL be the ticket's `role`, falling back to
its station's label when the role is unset, and the component SHALL list the ticket's tasks as
read-only sub-lines so the cook sees the station's itemized work for the dish (both in the
docket's component rows and in the my-station list). Advancing a component SHALL move its ticket
strictly forward (`pending → in_progress → ready`); a `ready` component SHALL offer no further
action; tasks SHALL NOT be individually checkable — status, timers and alerts stay per
component. A dish reads done only when all its components are done. Each dish row SHALL surface
an alert severity derived from its components' waiting times (calm → warning → overdue).
Dockets SHALL be ordered alerted-work-first (by severity), and within equal severity **newest
first** (latest fired on top). Fully-ready dockets SHALL be hidden from the board by default and
shown on demand via a "Listas (N)" toggle carrying their live count; when shown, they sort after
the unfinished work.

#### Scenario: A dish routed to several stations shows its components

- **WHEN** an order item's product is mapped to two stations with roles (e.g. "Parrilla" and
  "Fríos") and the order is routed
- **THEN** the docket shows one dish with two components named by those roles, each advancing
  its own ticket independently

#### Scenario: A component lists its station's tasks

- **WHEN** a ticket carries tasks (e.g. "Carne de hamburguesa", "Tocineta ahumada")
- **THEN** its component shows them as read-only sub-lines in the docket and in my-station, and
  tapping still advances the whole component, never one task

#### Scenario: Component without tasks renders as before

- **WHEN** a ticket carries no tasks
- **THEN** the component shows only its name, with no empty task area

#### Scenario: Component without a role falls back to the station label

- **WHEN** a ticket's `role` is null
- **THEN** its component is named after its station's label

#### Scenario: Dish is done only when all components are done

- **WHEN** one of a dish's two components is `ready` and the other is not
- **THEN** the dish reads as in progress, and the cross-station alert layer may flag the
  finished component as getting cold

#### Scenario: Advance moves a ticket forward

- **WHEN** the cook taps a `pending` component
- **THEN** its ticket moves to `in_progress`; tapping again moves it to `ready`

#### Scenario: Ready components are terminal

- **WHEN** a component's ticket is `ready`
- **THEN** tapping it performs no mutation and the component reads as done

#### Scenario: Newest orders surface first, alerts still win

- **WHEN** the board shows a calm just-fired docket, an older calm docket, and an old docket
  with an urgent alert
- **THEN** the urgent docket shows first, then the just-fired one, then the older calm one

#### Scenario: Ready dockets hide behind the toggle

- **WHEN** an order's tickets all reach `ready` while the "Listas" toggle is off
- **THEN** its docket leaves the board and the toggle's count increases; turning the toggle on
  shows it after the unfinished dockets, and turning it off hides it again

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
