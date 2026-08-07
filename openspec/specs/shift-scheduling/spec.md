# shift-scheduling Specification

## Purpose
TBD - created by archiving change staff-shift-scheduling. Update Purpose after archive.
## Requirements
### Requirement: Recurring shift templates

The system SHALL allow authorized users (`staff.manage`) to define one recurring weekly shift template per employee, consisting of the weekdays worked (`0=Sun`..`6=Sat`), a `start_time`, an `end_time`, a `valid_from` date and an optional `valid_until` (null = indefinite). The `end_time` MUST be after the `start_time`, and the employee MUST belong to the current tenant. Weekdays omitted from the template are rest days that produce no shift.

#### Scenario: Create a template

- **WHEN** an authorized user creates a template for an existing employee with valid weekdays and start_time before end_time
- **THEN** the system persists the template scoped to the tenant and branch and returns it

#### Scenario: Reject inverted time range

- **WHEN** a user submits a template whose end_time is not after its start_time
- **THEN** the system responds with a validation error and no template is created

#### Scenario: Indefinite validity

- **WHEN** a template is created with `valid_until` null
- **THEN** the template SHALL be treated as recurring indefinitely until an admin changes it

### Requirement: Materialize shifts over a rolling horizon

The system SHALL generate concrete `planned_shift` rows from an employee's active template for every matching weekday between the template's coverage start and a horizon of 90 days ahead, tracking a `generated_through` watermark. Generation MUST be idempotent: re-running SHALL NOT create a second shift for the same `(tenant, employee, date)`.

#### Scenario: Generate the horizon

- **WHEN** a template is created or generation is run
- **THEN** the system creates `planned_shift` rows for each matching date up to 90 days ahead
- **AND** advances `generated_through` to the horizon date

#### Scenario: Idempotent regeneration

- **WHEN** generation runs again over an already-covered range
- **THEN** no duplicate shift is created for any `(employee, date)` already materialized

#### Scenario: Rest days produce no shift

- **WHEN** a weekday is not included in the employee's template
- **THEN** no shift is generated for that weekday

### Requirement: Extend the generation horizon

The system SHALL provide an action to extend materialization by another 90 days beyond the current `generated_through`, repeatable, so an indefinite schedule can be advanced on demand.

#### Scenario: Extend by 90 days

- **WHEN** an authorized user extends the horizon
- **THEN** the system generates the next 90-day window of shifts and advances `generated_through`

### Requirement: Regeneration preserves resolved shifts

When a template is edited, the system SHALL regenerate future shifts (dates on or after the effective date) but MUST NOT overwrite or delete shifts whose `status` is not `scheduled` or whose `origin` is not `template`. Past shifts SHALL be immutable.

#### Scenario: Edit preserves approved day-off

- **WHEN** an admin edits a template and a future date already has a shift with `status = day_off`
- **THEN** that day-off shift is preserved unchanged after regeneration

#### Scenario: Edit preserves coverage and manual shifts

- **WHEN** regeneration runs and a future date has a shift with `origin = coverage` or `origin = manual`
- **THEN** that shift is preserved unchanged

#### Scenario: Past shifts unchanged

- **WHEN** a template is edited
- **THEN** shifts dated before the effective date are not modified

### Requirement: Day off and special hours as shift status

The system SHALL represent a day off, a special-hours adjustment and a manual reinforcement as state on the shift via `status` (`scheduled | day_off | covered | manual`), `origin` (`template | manual | coverage`) and an optional `note`, rather than as separate records. Marking a scheduled shift as a day off SHALL set `status = day_off`.

#### Scenario: Mark a day off

- **WHEN** an authorized user marks a scheduled shift as a day off with a reason
- **THEN** the shift's `status` becomes `day_off` and the reason is stored in `note`

#### Scenario: Create a manual reinforcement shift

- **WHEN** an authorized user creates a one-off shift outside the template pattern
- **THEN** the system creates a shift with `origin = manual` and `status = manual` for that date

### Requirement: Coverage assignment preserves the audit trail

When a substitute covers an absent employee for a date, the system SHALL keep the absent employee's shift as `status = day_off` and create a new shift for the substitute with `status = covered`, `origin = coverage` and `covered_by_employee_id` referencing the absent employee. The substitute MUST be available that date.

#### Scenario: Assign coverage

- **WHEN** an authorized user assigns an available substitute to cover an absent employee's date
- **THEN** a new `covered` shift is created for the substitute referencing the absent employee
- **AND** the absent employee's shift remains `day_off`

#### Scenario: Availability for coverage

- **WHEN** the system lists employees available to cover a date
- **THEN** it returns active branch employees whose template does not schedule that weekday and who have no shift on that date

### Requirement: Time-off request workflow

The system SHALL allow recording a time-off request (`employee_id`, `date`, `reason`) with a lifecycle `pending | approved | rejected`, recording `decided_by` and `decided_at` on decision. Approving a request SHALL set the target shift to `day_off` and MAY assign coverage. Rejecting SHALL record a reason and leave the shift scheduled.

#### Scenario: Submit a request

- **WHEN** a request is created for an employee and date
- **THEN** it is persisted with `status = pending`

#### Scenario: Approve with coverage

- **WHEN** an authorized user approves a pending request and assigns an available substitute
- **THEN** the request becomes `approved`, the shift becomes `day_off`, and a coverage shift is created for the substitute

#### Scenario: Approve without coverage

- **WHEN** an authorized user approves a request without assigning coverage
- **THEN** the request becomes `approved`, the shift becomes `day_off`, and the slot is reported as uncovered

#### Scenario: Reject a request

- **WHEN** an authorized user rejects a pending request with a reason
- **THEN** the request becomes `rejected`, the reason is stored, and the shift stays `scheduled`

### Requirement: Week-range shift read endpoint

The system SHALL expose a branch-scoped, date-range read of shifts (`from`, `to`) returning all shifts for the branch across employees within the window, so a weekly calendar can be rendered in one call. Requires `staff.read` and is tenant-scoped.

#### Scenario: Read a week of shifts

- **WHEN** an authorized user requests shifts for a branch between two dates
- **THEN** the system returns every shift in that window for the branch, including day-off and coverage shifts

#### Scenario: List time-off requests by status

- **WHEN** an authorized user lists time-off requests for a branch filtered by status
- **THEN** only requests for that tenant and branch matching the status are returned

