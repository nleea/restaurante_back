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
an alert severity derived from its components' waiting times (calm → warning → overdue) and
dockets SHALL be ordered so the most urgent, oldest work surfaces first, with fully-ready
dockets de-emphasised and sorted last.

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

#### Scenario: Urgent work surfaces first

- **WHEN** the board shows several dockets
- **THEN** unfinished dockets appear ordered by urgency/age and a docket whose tickets are all
  `ready` sinks below the unfinished ones

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
