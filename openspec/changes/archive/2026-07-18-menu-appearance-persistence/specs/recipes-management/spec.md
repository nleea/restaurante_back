## MODIFIED Requirements

### Requirement: Manage ingredients

The system SHALL allow authorized users to create, list, retrieve, update and deactivate ingredients. Each ingredient has a name, a unit of measure, an optional free-text category (≤ 50 characters, trimmed on save), an active flag, and an `is_customer_removable` flag (default `true`) marking whether a customer may exclude it from a dish. The `unit_of_measure_id` MUST reference an existing unit.

#### Scenario: Create an ingredient
- **WHEN** an authorized user creates an ingredient with a name and an existing `unit_of_measure_id`
- **THEN** the system persists the ingredient with `is_active` true and `is_customer_removable` true and returns 201 with the created record

#### Scenario: Create an ingredient with a category
- **WHEN** an authorized user creates or updates an ingredient with a `category`
- **THEN** the category is persisted (trimmed) and returned on subsequent reads

#### Scenario: Mark an ingredient non-removable
- **WHEN** an authorized user sets `is_customer_removable` to false on an ingredient (e.g. salt, oil)
- **THEN** the flag is persisted and returned on subsequent reads, so consumers can exclude it from customer-facing removable lists

#### Scenario: Reject unknown unit of measure
- **WHEN** a user creates or updates an ingredient with a `unit_of_measure_id` that does not exist
- **THEN** the system responds 404 Not Found for the unit

#### Scenario: List ingredients
- **WHEN** an authorized user lists ingredients, optionally filtering by active state
- **THEN** the system returns the tenant's ingredients matching the filter, each including its `category` when set and its `is_customer_removable` flag

#### Scenario: Deactivate an ingredient
- **WHEN** an authorized user deactivates an existing ingredient
- **THEN** the ingredient's `is_active` becomes false
- **AND** the ingredient remains retrievable
