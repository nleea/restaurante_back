## MODIFIED Requirements

### Requirement: Manage planned shifts

The system SHALL allow authorized users to schedule, list, update and delete planned shifts for an employee on a given date with a start and end time. The shift's `end_time` MUST be after its `start_time`, and the employee MUST belong to the current tenant. Each shift SHALL carry a `status` (`scheduled | day_off | covered | manual`), an `origin` (`template | manual | coverage`), an optional `covered_by_employee_id` (set when `status = covered`) and an optional `note`. A `(tenant, employee, date)` slot SHALL be unique. In addition to the per-employee listing, the system SHALL support a branch-scoped date-range read of shifts.

#### Scenario: Schedule a shift

- **WHEN** an authorized user schedules a shift for an existing employee with start_time before end_time
- **THEN** the system persists the planned shift with `status = scheduled` (or `manual` for one-off shifts) and returns it including its status, origin and covered_by fields

#### Scenario: Reject inverted time range

- **WHEN** a user schedules a shift whose end_time is not after its start_time
- **THEN** the system responds with a validation error
- **AND** no shift is created

#### Scenario: List shifts for an employee

- **WHEN** an authorized user lists planned shifts for an employee
- **THEN** only that employee's shifts within the current tenant are returned, each including status, origin and covered_by

#### Scenario: List shifts for a branch by date range

- **WHEN** an authorized user lists shifts for a branch between two dates
- **THEN** the system returns all shifts for that branch and tenant within the range, across employees

#### Scenario: Reject duplicate slot

- **WHEN** a shift is created for a `(employee, date)` that already has a shift
- **THEN** the system rejects the duplicate rather than creating a second row for the slot
