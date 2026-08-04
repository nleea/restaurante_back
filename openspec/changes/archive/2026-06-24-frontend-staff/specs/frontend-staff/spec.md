## ADDED Requirements

### Requirement: Staff route is permission-gated

The system SHALL expose a `/staff` route that requires authentication and the `staff.read` permission, and SHALL surface a "Personal" navigation entry only when the user holds `staff.read`. Mutating controls within the screen SHALL be additionally gated by `staff.manage`. This gating is UX; the backend enforces authorization independently.

#### Scenario: Authorized user reaches the staff screen

- **WHEN** an authenticated user with `staff.read` navigates to `/staff`
- **THEN** the staff screen renders and the "Personal" nav entry is visible

#### Scenario: Unauthorized user is blocked

- **WHEN** an authenticated user without `staff.read` navigates to `/staff`
- **THEN** the router redirects to the Forbidden view and the "Personal" nav entry is hidden

### Requirement: Employees are listed with human labels

The screen SHALL list the tenant's employees and SHALL resolve their raw identifiers into human-readable labels: the linked user's name/email (via `GET /rbac/users`), the role name (via `GET /rbac/roles`), and the branch name (via the active-branch context / `GET /branches`). The list SHALL allow filtering by active state, and SHALL scope to the active branch by default while still allowing the employee's own branch to be shown.

#### Scenario: Employee rows show names, not UUIDs

- **WHEN** the employee list loads
- **THEN** each row shows the employee's name/email, role name, branch name, and active state, with no raw UUIDs

#### Scenario: Filter by active state

- **WHEN** the user filters to active employees only
- **THEN** deactivated employees are omitted from the list

### Requirement: Add an employee

The screen SHALL provide an "Add employee" action (gated by `staff.manage`) that, in one flow, provisions a user with an inline person (`POST /rbac/users` with first/last name, email, password, and the chosen role) and then creates the employee (`POST /staff/employees`) for the active branch and that role. On success the new employee SHALL appear in the list.

#### Scenario: Successful employee creation

- **WHEN** the user submits the add-employee form with name, email, password, branch, and role
- **THEN** the system provisions the user+person and creates the employee, and the new employee appears in the list with its labels resolved

#### Scenario: Duplicate email surfaces an error

- **WHEN** the chosen email already belongs to a tenant user
- **THEN** the form shows the conflict error and no employee is added

### Requirement: Change role and deactivate an employee

The screen SHALL let an authorized user change an employee's role (`PATCH /staff/employees/{id}/role`, choosing from `GET /rbac/roles`) and deactivate an employee (`DELETE /staff/employees/{id}`). The displayed state SHALL update to reflect the change.

#### Scenario: Role change is reflected

- **WHEN** the user selects a different role for an employee and confirms
- **THEN** the employee's role label updates to the new role

#### Scenario: Deactivation is reflected

- **WHEN** the user deactivates an employee
- **THEN** the employee is shown as inactive (and is hidden when filtering to active only)

### Requirement: Manage an employee's planned shifts

For a selected employee, the screen SHALL list planned shifts and let an authorized user create, edit, and delete them. A shift SHALL carry a date, a start time, and an end time, and the create/edit controls SHALL enforce that the end time is after the start time before submitting.

#### Scenario: Create a valid shift

- **WHEN** the user adds a shift with a date and an end time later than the start time
- **THEN** the shift is created and appears in the employee's shift list

#### Scenario: Invalid time range is prevented

- **WHEN** the user enters an end time at or before the start time
- **THEN** the form blocks submission and explains the constraint

#### Scenario: Delete a shift

- **WHEN** the user deletes a planned shift
- **THEN** the shift is removed from the employee's shift list
