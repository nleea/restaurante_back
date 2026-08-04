# frontend-kitchen (delta)

## MODIFIED Requirements

### Requirement: Cook-facing ticket board

The KitchenView SHALL present the board as KDS order dockets: each order's tickets grouped into
one docket showing the destination (table number or channel) and an order reference. Within a
docket, tickets SHALL be grouped by order item: one dish row per order item (label and quantity
from the store's resolution, degrading to a short ticket reference when unresolvable), with one
tappable component per ticket. A component's name SHALL be the ticket's `role`, falling back to
its station's label when the role is unset. Advancing a component SHALL move its ticket strictly
forward (`pending → in_progress → ready`); a `ready` component SHALL offer no further action; a
dish reads done only when all its components are done. Each dish row SHALL surface an alert
severity derived from its components' waiting times (calm → warning → overdue) and dockets SHALL
be ordered so the most urgent, oldest work surfaces first, with fully-ready dockets
de-emphasised and sorted last.

#### Scenario: A dish routed to several stations shows its components

- **WHEN** an order item's product is mapped to two stations with roles (e.g. "Parrilla" and
  "Fríos") and the order is routed
- **THEN** the docket shows one dish with two components named by those roles, each advancing
  its own ticket independently

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

## REMOVED Requirements

### Requirement: Recipe affordances hidden

**Reason**: A backend recipe source now exists (recipe details + card in `recipes-management`),
so hiding the drawer is no longer required.
**Migration**: Replaced by "Recipe drawer on real data" below; the `RECIPES_ENABLED` flag turns
on and the drawer loads the card endpoint instead of mock data.

## ADDED Requirements

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
