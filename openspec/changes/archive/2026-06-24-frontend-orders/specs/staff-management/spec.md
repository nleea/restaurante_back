## ADDED Requirements

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
