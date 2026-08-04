## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Assignment and delivery lifecycle

The system SHALL support an explicit delivery lifecycle. Assigning a delivery to a `preparing` run sets the delivery's route and run and moves it to `assigned`. Departing a run moves it `preparing → in_transit` (stamping `departed_at`) and moves its `assigned` deliveries to `in_transit`. A delivery SHALL be markable `delivered` only from `in_transit`, and markable `not_delivered` from **any non-terminal state** (`pending`, `assigned` or `in_transit`), stamping `delivered_at`; marking `not_delivered` SHALL accept and persist an optional reason (from a fixed list) and an optional free-text comment. Finishing a run moves it `in_transit → finished`. Backward transitions and transitions out of a terminal state (`delivered`, `not_delivered`) SHALL be rejected.

Allowing `not_delivered` from any non-terminal state is what guarantees every delivery can reach an ending: an order that was cooked and never left would otherwise be unresolvable, and would block its shift's cash session forever.

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
- **WHEN** a user marks a `delivered` or `not_delivered` delivery again
- **THEN** the system responds with a conflict error

#### Scenario: Finish a run
- **WHEN** an authorized user finishes an `in_transit` run
- **THEN** the run becomes `finished` with `finished_at` set

#### Scenario: Reject finishing a non-in-transit run
- **WHEN** a user finishes a run that is not `in_transit`
- **THEN** the system responds with a conflict error
