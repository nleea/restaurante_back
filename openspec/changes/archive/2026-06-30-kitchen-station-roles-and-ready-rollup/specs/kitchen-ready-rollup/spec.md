## ADDED Requirements

### Requirement: Order kitchen readiness is derived from its tickets

The system SHALL derive an order's kitchen readiness as one of `none | in_kitchen | ready`:
`none` before the order has any kitchen ticket; `in_kitchen` while at least one non-cancelled ticket
of the order is not `ready`; `ready` when every non-cancelled ticket of the order is `ready`. This
readiness SHALL be a derivation over the order's tickets, never a manually toggled flag, so it is
always consistent with the board.

#### Scenario: Order with mixed ticket states is in the kitchen

- **WHEN** an order has tickets where at least one is not `ready`
- **THEN** its kitchen readiness is `in_kitchen`

#### Scenario: All tickets ready means the order is ready

- **WHEN** every non-cancelled ticket of an order is `ready`
- **THEN** its kitchen readiness is `ready`

#### Scenario: An order never routed has no kitchen state

- **WHEN** an order has no kitchen tickets
- **THEN** its kitchen readiness is `none`

### Requirement: Advancing the last ticket marks the order ready

The system SHALL, when advancing a ticket to `ready` makes it the last non-cancelled ticket of its
order to reach `ready`, emit a readiness signal to the orders side via a dedicated outbound port
(symmetric to the existing orders-to-kitchen routing port) that sets the order's `kitchen_state` to
`ready`. This signal SHALL be a non-blocking side effect: a failure to notify orders SHALL NOT fail
the ticket advance.

#### Scenario: Last ready ticket notifies orders

- **WHEN** the final unfinished ticket of an order is advanced to `ready`
- **THEN** the order's `kitchen_state` becomes `ready`

#### Scenario: Notification failure does not break the board

- **WHEN** the readiness notification to orders fails
- **THEN** the ticket is still advanced to `ready` and the board reflects it

### Requirement: Adding an item after ready returns the order to in-kitchen

The system SHALL recompute an order's `kitchen_state` to `in_kitchen` when a new item is added to an
order that was already `ready` and its auto-route creates fresh `pending` tickets, so readiness never
lies about food that is not actually done.

#### Scenario: New item reopens the kitchen state

- **WHEN** an item is added to an order whose `kitchen_state` was `ready`
- **THEN** new tickets are routed and the order's `kitchen_state` returns to `in_kitchen`

### Requirement: Readiness is surfaced to the right audience by channel

The system SHALL surface an order's `kitchen_state` to the audience that acts on it, by channel. For
`dine_in`, the Salón table card SHALL show progress while in the kitchen (count of ready vs total
tickets) and a clear "ready to serve" affordance when `ready`. For `takeaway`, the no-table strip
SHALL show the same readiness as "ready to hand off". For `delivery`, readiness SHALL additionally
trigger the automatic dispatch entry described below. The permission gates of each surface are
unchanged.

#### Scenario: Dine-in ready reaches the waiter

- **WHEN** a dine-in order becomes `ready`
- **THEN** its Salón table card shows a "ready to serve" state instead of a plain occupied state

#### Scenario: Takeaway ready reaches the counter

- **WHEN** a takeaway order becomes `ready`
- **THEN** it is shown as "ready to hand off" in the no-table strip

#### Scenario: In-kitchen progress is visible

- **WHEN** a dine-in order has 2 of 3 tickets ready
- **THEN** its table card shows in-kitchen progress reflecting 2 of 3

### Requirement: A ready delivery order enters dispatch automatically

The system SHALL, when a `delivery` order becomes `ready`, automatically create that order's delivery
record via an outbound port to the delivery module so it enters Dispatch as `pending` (ready to
assign a driver), with no manual step. This creation SHALL be idempotent (SHALL NOT create a second
record if one already exists for the order) and SHALL be a non-blocking side effect that does not
fail the ticket advance or the readiness update. Grouping deliveries into a delivery run SHALL remain
a manual Dispatch action.

#### Scenario: Delivery ready is auto-dispatched

- **WHEN** a `delivery` order becomes `ready` and has no delivery record yet
- **THEN** a delivery record is created for it and appears in Dispatch as `pending`

#### Scenario: Auto-dispatch is idempotent

- **WHEN** a `delivery` order that already has a delivery record becomes `ready` (e.g. re-computed)
- **THEN** no second delivery record is created

#### Scenario: Dispatch-create failure does not break the kitchen

- **WHEN** creating the delivery record fails
- **THEN** the order still reaches `ready` and the ticket advance still succeeds

### Requirement: Live kitchen timers from existing timestamps

The system SHALL surface live times computed from the ticket's existing `entered_at` and `ready_at`,
without introducing new backend timestamps: on the KDS, each ticket's elapsed time since it entered
the station, escalating past configurable thresholds (e.g. amber, then red); and on the Salón
surfaces, a "waiting on kitchen" time while `in_kitchen` and a "ready since" (cooling for dine-in,
awaiting-driver for delivery) time once `ready`. Timers SHALL respect reduced-motion and never block
rendering when a timestamp is missing.

#### Scenario: KDS ticket ages after firing

- **WHEN** a ticket has been at a station past the amber threshold
- **THEN** its KDS chit shows the elapsed time in the escalated (amber/red) style

#### Scenario: Ready order shows how long it has been waiting to be taken

- **WHEN** an order has been `ready` for several minutes without being served/dispatched
- **THEN** its Salón surface shows a "ready since" time that escalates over time

#### Scenario: Missing timestamp degrades gracefully

- **WHEN** a ticket has no `entered_at`
- **THEN** no timer is shown for it and the rest of the chit renders normally
