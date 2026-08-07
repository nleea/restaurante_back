## MODIFIED Requirements

### Requirement: Manage ingredients

The system SHALL allow authorized users to create, list, retrieve, update and deactivate ingredients. Each ingredient has a name, a unit of measure, an optional free-text category (≤ 50 characters, trimmed on save), an active flag, an `is_customer_removable` flag (default `true`) marking whether a customer may exclude it from a dish, and an optional `default_station_id` naming the kitchen station where that ingredient is worked. The `unit_of_measure_id` MUST reference an existing unit, and `default_station_id`, when given, MUST reference an existing kitchen station of the tenant.

#### Scenario: Create an ingredient
- **WHEN** an authorized user creates an ingredient with a name and an existing `unit_of_measure_id`
- **THEN** the system persists the ingredient with `is_active` true, `is_customer_removable` true and `default_station_id` null, and returns 201 with the created record

#### Scenario: Create an ingredient with a category
- **WHEN** an authorized user creates or updates an ingredient with a `category`
- **THEN** the category is persisted (trimmed) and returned on subsequent reads

#### Scenario: Mark an ingredient non-removable
- **WHEN** an authorized user sets `is_customer_removable` to false on an ingredient (e.g. salt, oil)
- **THEN** the flag is persisted and returned on subsequent reads, so consumers can exclude it from customer-facing removable lists

#### Scenario: Assign a default kitchen station to an ingredient
- **WHEN** an authorized user creates or updates an ingredient with a `default_station_id` referencing an existing kitchen station
- **THEN** the station is persisted and returned on subsequent reads, so the kitchen module can derive which station prepares a dish from its recipe

#### Scenario: Clear an ingredient's default station
- **WHEN** an authorized user updates an ingredient setting `default_station_id` to null
- **THEN** the ingredient is persisted without a station and later suggestions report it as unassigned

#### Scenario: Reject unknown kitchen station
- **WHEN** a user creates or updates an ingredient with a `default_station_id` that does not exist in the tenant
- **THEN** the system responds 404 Not Found for the station and the ingredient is left unchanged

#### Scenario: Deleting a kitchen station does not delete its ingredients
- **WHEN** a kitchen station referenced as some ingredients' default is deleted
- **THEN** those ingredients survive with `default_station_id` set to null

#### Scenario: Reject unknown unit of measure
- **WHEN** a user creates or updates an ingredient with a `unit_of_measure_id` that does not exist
- **THEN** the system responds 404 Not Found for the unit

#### Scenario: List ingredients
- **WHEN** an authorized user lists ingredients, optionally filtering by active state
- **THEN** the system returns the tenant's ingredients matching the filter, each including its `category` when set, its `is_customer_removable` flag and its `default_station_id` when set

#### Scenario: Deactivate an ingredient
- **WHEN** an authorized user deactivates an existing ingredient
- **THEN** the ingredient's `is_active` becomes false
- **AND** the ingredient remains retrievable
