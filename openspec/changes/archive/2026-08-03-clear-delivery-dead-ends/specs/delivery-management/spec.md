## MODIFIED Requirements

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

## ADDED Requirements

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
