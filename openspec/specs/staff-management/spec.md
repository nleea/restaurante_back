# staff-management

## Purpose

Branch-scoped workforce management for the restaurant SaaS: employees (linking a
person, a login user and a role to a branch), planned shifts, attendance
(clock-in/out) and commissions. Fully tenant-isolated and RBAC-protected.
## Requirements
### Requirement: Tenant isolation for all staff data

The system SHALL scope every staff read and write to the `tenant_id` resolved by the subdomain middleware. No request SHALL be able to read or mutate staff records belonging to another tenant.

#### Scenario: Tenant cannot read another tenant's employees
- **WHEN** a request authenticated for tenant A lists employees
- **THEN** the response contains only employees whose `tenant_id` equals tenant A
- **AND** employees of tenant B are never returned

#### Scenario: Cross-tenant lookup by id is treated as not found
- **WHEN** a request for tenant A fetches an employee id that belongs to tenant B
- **THEN** the system responds 404 Not Found
- **AND** no data from tenant B is leaked

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a staff endpoint is called and no tenant was resolved by the middleware
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Branch scoping for branch-level staff entities

The system SHALL store and validate a `branch_id` for `employees` and `planned_shifts`. The provided `branch_id` MUST belong to the current tenant; otherwise the operation SHALL fail.

#### Scenario: Create employee on a valid branch
- **WHEN** an authorized user creates an employee with a `branch_id` belonging to the current tenant
- **THEN** the employee is persisted with that tenant_id and branch_id

#### Scenario: Create employee with a branch from another tenant
- **WHEN** a user creates an employee referencing a `branch_id` that does not belong to the current tenant
- **THEN** the system responds 404 Not Found for the branch
- **AND** no employee is created

### Requirement: Manage employees

The system SHALL allow authorized users to create, list, retrieve, update and deactivate employees. An employee links exactly one `person`, one login `user`, and one `role`, all of which MUST exist in the current tenant. `person_id` and `user_id` SHALL be unique.

#### Scenario: Create an employee
- **WHEN** an authorized user submits a valid person_id, user_id, role_id and branch_id
- **THEN** the system creates the employee with `is_active` true and returns 201 with the created record

#### Scenario: Reject duplicate person or user
- **WHEN** a user creates an employee whose person_id or user_id is already linked to another employee
- **THEN** the system responds with a conflict error
- **AND** no duplicate employee is created

#### Scenario: Reject unknown references
- **WHEN** a user creates an employee with a person_id, user_id or role_id that does not exist in the tenant
- **THEN** the system responds 404 Not Found identifying the missing reference

#### Scenario: Deactivate an employee
- **WHEN** an authorized user deactivates an existing employee
- **THEN** the employee's `is_active` becomes false
- **AND** the employee remains retrievable for history

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

### Requirement: Record attendance

The system SHALL allow authorized users to record an employee clock-in and later clock-out, optionally linked to a planned shift. `check_out_at` MUST be after `check_in_at` when set, and an employee MUST NOT have more than one open attendance (no `check_out_at`) at a time.

#### Scenario: Clock in
- **WHEN** an authorized user records a check-in for an employee with no open attendance
- **THEN** the system creates an attendance with `check_in_at` set and `check_out_at` null

#### Scenario: Reject second open attendance
- **WHEN** a user records a check-in for an employee who already has an open attendance
- **THEN** the system responds with a conflict error

#### Scenario: Clock out
- **WHEN** an authorized user records a check-out for an open attendance with a time after the check-in
- **THEN** the attendance's `check_out_at` is set

#### Scenario: Reject invalid clock-out time
- **WHEN** a user records a check-out earlier than the check-in
- **THEN** the system responds with a validation error
- **AND** the attendance remains open

### Requirement: Record commissions

The system SHALL allow authorized users to register a commission for an employee with a type, a positive amount, an optional loose `reference_id`, and an occurrence timestamp, and to list commissions for an employee.

#### Scenario: Register a commission
- **WHEN** an authorized user registers a commission for an existing employee with a positive amount
- **THEN** the system persists the commission and returns it

#### Scenario: Reject non-positive amount
- **WHEN** a user registers a commission with an amount that is zero or negative
- **THEN** the system responds with a validation error

#### Scenario: List commissions for an employee
- **WHEN** an authorized user lists commissions for an employee
- **THEN** only that employee's commissions within the current tenant are returned

### Requirement: RBAC protection of staff endpoints

The system SHALL require the `staff.read` permission for all staff read endpoints and the `staff.manage` permission for all staff write endpoints.

#### Scenario: Read without permission
- **WHEN** a user lacking `staff.read` calls a staff read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `staff.manage` calls a staff write endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

### Requirement: Resolve the current user's employee

The system SHALL expose `GET /staff/employees/me` that returns the employee record linked to the authenticated user for the resolved tenant. The endpoint SHALL require an authenticated session but SHALL NOT require the `staff.read` permission, since an order-taker must resolve their own `employee_id` to operate orders. The response SHALL include the employee's `id`, `branch_id`, `role_id`, and `is_active`. When the authenticated user is not linked to any employee, the endpoint SHALL respond `404`.

#### Scenario: Authenticated employee resolves itself

- **WHEN** an authenticated user who is linked to an employee requests `GET /staff/employees/me`
- **THEN** the system responds `200` with that employee's `id`, `branch_id`, `role_id`, and `is_active`

#### Scenario: Order-taker without staff.read still resolves

- **WHEN** a user holding `orders.*` but not `staff.read` requests `GET /staff/employees/me`
- **THEN** the system responds `200` with their employee (the endpoint is not gated by `staff.read`)

#### Scenario: User is not an employee

- **WHEN** an authenticated user not linked to any employee requests `GET /staff/employees/me`
- **THEN** the system responds `404`

#### Scenario: Unauthenticated request is rejected

- **WHEN** `GET /staff/employees/me` is called without a valid access token
- **THEN** the system responds `401`

