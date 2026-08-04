## ADDED Requirements

### Requirement: Weekly line-up board over real shifts

The `/shifts` Calendario SHALL render the active branch's week from the range read endpoint, one row per active employee and one column per day, resolving each cell from the real shift's `status` (scheduled → working, day_off → día libre, covered → covering/cubierto, manual → refuerzo) and showing no shift on rest days. Employee names SHALL be resolved via the existing identity/RBAC resolution; employee color and operational role tag are out of scope. The view SHALL be gated by `staff.read` with mutations gated by `staff.manage`.

#### Scenario: Render the week from real data

- **WHEN** an authorized user opens `/shifts` for the active branch
- **THEN** the board shows each employee's real shifts for the week with times and coverage state

#### Scenario: Navigate weeks

- **WHEN** the user moves to the previous or next week
- **THEN** the board re-reads shifts for the new range and re-renders

#### Scenario: Read-only without manage permission

- **WHEN** a user has `staff.read` but not `staff.manage`
- **THEN** shift-mutating actions are hidden or disabled

### Requirement: Coverage readout per day

The Calendario SHALL show, per day column, a coverage summary (on-duty count, days off, uncovered count) computed over the branch roster, and SHALL visually signal a day with any uncovered shift.

#### Scenario: Show uncovered day

- **WHEN** a day has an approved day-off shift with no coverage
- **THEN** the day's column reports the uncovered count and is visually flagged

### Requirement: Manage shifts from the calendar

The Calendario SHALL let an authorized user create a manual shift, mark a shift as a day off, assign coverage from available employees, edit a shift's hours, and remove a shift, each persisting through the shift API and updating the board.

#### Scenario: Mark a day off with optional coverage

- **WHEN** the user marks a shift as a day off and optionally picks an available substitute
- **THEN** the shift becomes a día libre and, if chosen, a coverage shift appears for the substitute

#### Scenario: Create a manual shift

- **WHEN** the user creates a one-off shift for an employee, date, hours and note
- **THEN** the shift is persisted and appears on the board as a reinforcement

### Requirement: Time-off requests inbox

The `/shifts` Solicitudes view SHALL list time-off requests for the active branch by status (pending/approved/rejected) and SHALL let an authorized user approve (optionally assigning available coverage) or reject (with a reason) a pending request, reflecting the outcome on the board.

#### Scenario: Approve a request

- **WHEN** an authorized user approves a pending request
- **THEN** the request moves to approved and the corresponding shift becomes a día libre

#### Scenario: Reject a request

- **WHEN** an authorized user rejects a pending request with a reason
- **THEN** the request moves to rejected and the shift stays scheduled

### Requirement: Template editor

The `/shifts` Plantillas view SHALL let an authorized user author or edit an employee's weekly template (weekdays, entry/exit times, validity), save it (triggering regeneration of future shifts), and extend the generation horizon by another 90 days.

#### Scenario: Save a template

- **WHEN** an authorized user saves a template for an employee
- **THEN** the template persists and future shifts are regenerated without overwriting approved days off or coverage

#### Scenario: Extend the horizon

- **WHEN** an authorized user chooses to extend the schedule
- **THEN** the next 90-day window of shifts is generated
