## ADDED Requirements

### Requirement: Tenant and branch isolation for inventory

The system SHALL scope every inventory read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate inventory of another tenant.

#### Scenario: Tenant cannot see another tenant's stock
- **WHEN** a request for tenant A lists stock for a branch
- **THEN** only stock rows whose `tenant_id` equals tenant A are returned

#### Scenario: Unknown branch is rejected
- **WHEN** a request registers a movement for a `branch_id` that does not belong to the current tenant
- **THEN** the system responds 404 Not Found for the branch
- **AND** no movement or stock change is persisted

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** an inventory endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: View stock

The system SHALL allow authorized users to list current stock for a branch and to retrieve the stock of a single ingredient at a branch, each showing on-hand quantity and reorder threshold.

#### Scenario: List stock for a branch
- **WHEN** an authorized user lists stock for a branch of the current tenant
- **THEN** the system returns one entry per ingredient that has a stock row, with `current_quantity` and `min_stock`

#### Scenario: Retrieve stock for an ingredient not yet tracked
- **WHEN** an authorized user requests stock for an ingredient/branch with no stock row
- **THEN** the system responds 404 Not Found

### Requirement: Low-stock view

The system SHALL allow authorized users to list stock rows where `current_quantity` is at or below `min_stock` for a branch, to drive reordering.

#### Scenario: Only at-or-below-threshold rows are returned
- **WHEN** an authorized user requests the low-stock view for a branch
- **THEN** the system returns only rows where `current_quantity <= min_stock`

### Requirement: Set reorder threshold

The system SHALL allow authorized users to set the `min_stock` reorder threshold for an ingredient at a branch. The threshold MUST be zero or greater. The ingredient MUST belong to the current tenant; the stock row is created if it does not yet exist (with on-hand zero).

#### Scenario: Set threshold for a tracked ingredient
- **WHEN** an authorized user sets `min_stock` to a non-negative value for an existing ingredient/branch
- **THEN** the stock row's `min_stock` is updated and returned

#### Scenario: Reject negative threshold
- **WHEN** a user sets `min_stock` to a negative value
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown ingredient
- **WHEN** a user sets a threshold for an `ingredient_id` not in the current tenant
- **THEN** the system responds 404 Not Found

### Requirement: Register stock movement

The system SHALL allow authorized users to register an inventory movement of type `in` or `out` for an ingredient at a branch, recording who performed it (`employee_id`), a reason, an optional `reference_id`, and optional notes. The movement and the resulting stock change MUST be persisted atomically. The stock row is created on the first movement. `quantity` MUST be greater than zero. The `ingredient_id` and `employee_id` MUST belong to the current tenant.

#### Scenario: Stock-in increases on-hand
- **WHEN** an authorized user registers an `in` movement of quantity Q for an ingredient/branch
- **THEN** the movement is recorded
- **AND** the stock's `current_quantity` increases by Q

#### Scenario: First movement creates the stock row
- **WHEN** an `in` movement is registered for an ingredient/branch that has no stock row
- **THEN** a stock row is created with `current_quantity` equal to Q and `min_stock` zero

#### Scenario: Stock-out decreases on-hand
- **WHEN** an authorized user registers an `out` movement of quantity Q not exceeding current on-hand
- **THEN** the movement is recorded
- **AND** the stock's `current_quantity` decreases by Q

#### Scenario: Reject stock-out exceeding on-hand
- **WHEN** a user registers an `out` movement whose quantity exceeds current on-hand
- **THEN** the system responds with a conflict error
- **AND** neither the movement nor the stock is changed

#### Scenario: Reject non-positive quantity
- **WHEN** a user registers a movement with quantity zero or negative
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown ingredient or employee
- **WHEN** a user registers a movement whose `ingredient_id` or `employee_id` is not in the current tenant
- **THEN** the system responds 404 Not Found identifying the missing reference

### Requirement: Physical recount adjustment

The system SHALL allow authorized users to set the absolute on-hand quantity of an ingredient at a branch to a counted value, recording the difference from the previous on-hand as an `adjustment` movement attributed to an employee. The counted value MUST be zero or greater.

#### Scenario: Recount records the delta
- **WHEN** an authorized user recounts an ingredient/branch with current on-hand 10 to a counted value of 8
- **THEN** the stock's `current_quantity` becomes 8
- **AND** an `adjustment` movement capturing the difference is recorded

#### Scenario: Reject negative counted value
- **WHEN** a user submits a counted value below zero
- **THEN** the system responds with a validation error

### Requirement: Movement history

The system SHALL allow authorized users to list the movement history for an ingredient at a branch, ordered most-recent first.

#### Scenario: List movements
- **WHEN** an authorized user lists movements for an ingredient/branch
- **THEN** only that tenant's movements for that ingredient and branch are returned, newest first

### Requirement: RBAC protection of inventory endpoints

The system SHALL require the `inventory.read` permission for inventory read endpoints and the `inventory.adjust` permission for inventory write endpoints.

#### Scenario: Read without permission
- **WHEN** a user lacking `inventory.read` calls an inventory read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `inventory.adjust` calls an inventory write endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
