## ADDED Requirements

### Requirement: Capture a driver's position trail for an active run

The system SHALL record a driver's positions as an append-only trail attached to their active run: an ordered sequence of timestamped points (`latitude`, `longitude`, `recorded_at`). A point SHALL be appended only for a run that is active (`preparing` or `in_transit`); appending to a `finished` run SHALL be rejected. The trail SHALL be tenant- and branch-scoped like every other delivery record.

#### Scenario: Append a position to an active run
- **WHEN** a driver pushes a position for their own active run
- **THEN** the point is appended to that run's trail with its recorded time

#### Scenario: The latest point is the current position
- **WHEN** several positions have been appended to a run
- **THEN** the most recent point by `recorded_at` is the current position and the ordered set is the trail

#### Scenario: A finished run stops accruing positions
- **WHEN** a driver pushes a position for a run that is `finished`
- **THEN** the system rejects it and the trail is unchanged

### Requirement: A driver pushes location only for their own run

Pushing a position SHALL require `delivery.drive` and SHALL append only to a run owned by the calling driver (`run.employee_id == the driver`). A driver SHALL NOT push a position to another driver's run.

#### Scenario: Push to own run succeeds
- **WHEN** a holder of `delivery.drive` pushes a position to a run they own
- **THEN** the point is appended

#### Scenario: Push to another driver's run is rejected
- **WHEN** a driver pushes a position to a run owned by a different employee
- **THEN** the system responds with a forbidden or not-found error and appends nothing

#### Scenario: Push without the driver permission is rejected
- **WHEN** a user lacking `delivery.drive` pushes a position
- **THEN** the system responds 403 Forbidden

### Requirement: The dispatcher reads active drivers' positions

The system SHALL expose, under `delivery.read` and scoped to the branch, each active run's position trail together with its current point and the time of that point, so the dispatcher can see where drivers are. Runs that are not active SHALL NOT appear in the live read.

#### Scenario: Read active drivers' trails
- **WHEN** a dispatcher with `delivery.read` reads active driver positions for a branch
- **THEN** the system returns, per active run, the trail, the current point, and its recorded time

#### Scenario: Reading requires the read permission
- **WHEN** a user lacking `delivery.read` reads driver positions
- **THEN** the system responds 403 Forbidden

#### Scenario: Only active runs are included
- **WHEN** a branch has both active and finished runs
- **THEN** the live read includes only the active runs' positions
