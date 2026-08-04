# finance-management

## Purpose

Operating-expense ledger: expense categories and branch expenses (rent, utilities,
supplies, miscellaneous). Complements sales (orders), cost of goods (purchasing)
and the cash drawer (cash) so a tenant can see its real cost base. Tenant/branch-
isolated and RBAC-protected.

Out of scope for this capability: posting an expense to the POS cash drawer (cash
`out`), consolidated P&L reporting, and recurring/scheduled expenses. Customer
store credit (fiado) lives in the `customers` capability, not here.

## Requirements

### Requirement: Tenant and branch isolation for finance

The system SHALL scope every finance read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate categories or expenses of another tenant.

#### Scenario: Tenant cannot see another tenant's expenses
- **WHEN** a request for tenant A lists expenses
- **THEN** only expenses whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches an expense id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a finance endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage expense categories

The system SHALL allow authorized users to create, list, update and deactivate expense categories for the tenant (name, active flag).

#### Scenario: Create a category
- **WHEN** an authorized user creates an expense category with a name
- **THEN** the category is persisted active and returned

#### Scenario: List categories
- **WHEN** an authorized user lists expense categories, optionally by active state
- **THEN** the tenant's matching categories are returned

#### Scenario: Deactivate a category
- **WHEN** an authorized user deactivates a category
- **THEN** the category's `is_active` becomes false

### Requirement: Record expenses

The system SHALL allow authorized users to record a branch expense with a category, a description, a positive amount, the registering employee, and an `incurred_at` timestamp (defaulting to now when omitted). The `branch_id`, `expense_category_id` and `employee_id` MUST belong to the current tenant.

#### Scenario: Record an expense
- **WHEN** an authorized user records an expense with a valid category, branch, employee and a positive amount
- **THEN** the expense is persisted and returned

#### Scenario: Reject non-positive amount
- **WHEN** a user records an expense with an amount of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown references
- **WHEN** a user records an expense whose `branch_id`, `expense_category_id` or `employee_id` does not exist in the tenant
- **THEN** the system responds 404 Not Found identifying the missing reference

### Requirement: View expenses

The system SHALL allow authorized users to list expenses (optionally filtered by branch and/or category) and to retrieve a single expense.

#### Scenario: List expenses filtered by branch
- **WHEN** an authorized user lists expenses for a branch of the current tenant
- **THEN** only that branch's expenses are returned

#### Scenario: Filter by category
- **WHEN** an authorized user lists expenses filtered by a category
- **THEN** only expenses of that category within the tenant are returned

### Requirement: RBAC protection of finance endpoints

The system SHALL require the `finance.read` permission for finance read endpoints and the `finance.manage` permission for all finance write endpoints (categories and expenses).

#### Scenario: Read without permission
- **WHEN** a user lacking `finance.read` calls a finance read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `finance.manage` tries to create a category or record an expense
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
