## ADDED Requirements

### Requirement: Finance service layer

The Finance API service SHALL expose typed functions covering the `/finance` endpoints: expense
categories — list (`GET /finance/categories`, optional `active` filter), create
(`POST /finance/categories`), and update/deactivate (`PATCH /finance/categories/{id}`, the same
endpoint renaming and flipping `is_active`); and expenses — list
(`GET /finance/expenses`, optional `branch_id` and `category_id` filters), get one
(`GET /finance/expenses/{id}`), and record (`POST /finance/expenses`). The `amount` SHALL be carried
as the backend sends it (string-encoded decimal) without lossy reformatting in transport.

#### Scenario: List categories with the active filter

- **WHEN** `listCategories(true)` is called
- **THEN** it GETs `/finance/categories` passing `active=true` and resolves with the array of
  `ExpenseCategory`

#### Scenario: Deactivate a category via patch

- **WHEN** `updateCategory(id, { is_active: false })` is called
- **THEN** it PATCHes `/finance/categories/{id}` and resolves with the updated `ExpenseCategory`

#### Scenario: List expenses scoped to a branch

- **WHEN** `listExpenses({ branchId, categoryId? })` is called
- **THEN** it GETs `/finance/expenses` passing `branch_id` (and `category_id` when given) and
  resolves with the array of `Expense`

#### Scenario: Record an expense

- **WHEN** `recordExpense({ branch_id, expense_category_id, description, amount, employee_id,
  incurred_at? })` is called
- **THEN** it POSTs `/finance/expenses` and resolves with the created `Expense`

### Requirement: Finance store with categories and branch expenses

The Finance store SHALL hold the tenant's expense categories and the active branch's expenses, load
the expense list scoped to the active branch, and resolve a category name for each expense.
Mutations (create/rename/deactivate category, record expense) SHALL be write-through: after a
successful call the store refetches the affected collection so server state is shown verbatim.

#### Scenario: Load expenses for the active branch

- **WHEN** the store loads finance data for the active branch
- **THEN** `expenses` holds that branch's expenses and `categories` holds the tenant's categories

#### Scenario: Recording an expense refreshes the list

- **WHEN** an expense is recorded
- **THEN** the store refetches the branch's expenses so the new expense appears without a manual
  reload

#### Scenario: Category name resolves for an expense

- **WHEN** an expense's `expense_category_id` maps to a known category
- **THEN** the screen shows that category's name, degrading to a short reference when unresolved

### Requirement: Expense total and per-category subtotals

The store SHALL derive client-side, from the loaded expenses, the total amount (summed in integer
cents) and a per-category subtotal breakdown, so the screen presents the branch's cost base.

#### Scenario: Total sums the listed expenses

- **WHEN** the branch has several expenses loaded
- **THEN** the derived total equals the sum of their amounts

#### Scenario: Subtotals group by category

- **WHEN** expenses span more than one category
- **THEN** each category's subtotal equals the sum of its expenses' amounts

### Requirement: Record and view expenses

The FinanceView SHALL list the active branch's expenses with an optional category filter and a
running total, and let an authorized user record an expense (category, description, positive amount,
registering employee, optional date); recording SHALL require the `finance.manage` permission and a
non-positive amount SHALL be prevented.

#### Scenario: Record an expense

- **WHEN** a user with `finance.manage` submits the expense form with a category, description,
  positive amount, and employee
- **THEN** the expense is recorded and appears in the branch's expense list

#### Scenario: Filter expenses by category

- **WHEN** the user selects a category filter
- **THEN** only that category's expenses for the branch are shown and the total reflects the filter

#### Scenario: Non-positive amount is prevented

- **WHEN** a user enters an amount of zero or less
- **THEN** the form blocks submission

### Requirement: Manage expense categories

The FinanceView SHALL list the tenant's expense categories with an active filter and let an
authorized user create a category, rename it, and deactivate it; these mutations SHALL require the
`finance.manage` permission.

#### Scenario: Create a category

- **WHEN** a user with `finance.manage` creates a category with a name
- **THEN** the category is created active and appears in the list

#### Scenario: Deactivate a category

- **WHEN** a user with `finance.manage` deactivates a category
- **THEN** the category's row reflects an inactive state

### Requirement: Permission gating and navigation

The Finance screen SHALL be reachable at `/finance` only for authenticated users with
`finance.read`, exposed via a navigation entry; the record-expense and category
create/rename/deactivate controls SHALL be shown only with `finance.manage`. This gating is UX — the
backend enforces authorization independently.

#### Scenario: Read-only finance user

- **WHEN** the current user has `finance.read` but not `finance.manage`
- **THEN** the expense list, total, and categories are visible read-only and no record-expense or
  category-management actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `finance.read` navigates to `/finance`
- **THEN** the router redirects them to the forbidden view
