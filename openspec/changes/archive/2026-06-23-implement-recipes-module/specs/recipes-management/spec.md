## ADDED Requirements

### Requirement: Tenant isolation for recipes data

The system SHALL scope every recipes read and write to the `tenant_id` resolved by the subdomain middleware. No request SHALL read or mutate ingredients or recipe items of another tenant.

#### Scenario: Tenant cannot see another tenant's ingredients
- **WHEN** a request for tenant A lists ingredients
- **THEN** only ingredients whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches an ingredient id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a recipes endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage ingredients

The system SHALL allow authorized users to create, list, retrieve, update and deactivate ingredients. Each ingredient has a name, a unit of measure, and an active flag. The `unit_of_measure_id` MUST reference an existing unit.

#### Scenario: Create an ingredient
- **WHEN** an authorized user creates an ingredient with a name and an existing `unit_of_measure_id`
- **THEN** the system persists the ingredient with `is_active` true and returns 201 with the created record

#### Scenario: Reject unknown unit of measure
- **WHEN** a user creates or updates an ingredient with a `unit_of_measure_id` that does not exist
- **THEN** the system responds 404 Not Found for the unit

#### Scenario: List ingredients
- **WHEN** an authorized user lists ingredients, optionally filtering by active state
- **THEN** the system returns the tenant's ingredients matching the filter

#### Scenario: Deactivate an ingredient
- **WHEN** an authorized user deactivates an existing ingredient
- **THEN** the ingredient's `is_active` becomes false
- **AND** the ingredient remains retrievable

### Requirement: Define a variant's bill of materials

The system SHALL allow authorized users to add ingredient lines to the recipe of a product variant, each with a positive `quantity` and a `unit_of_measure_id`. The `product_variant_id`, `ingredient_id` and `unit_of_measure_id` MUST exist in scope. An ingredient MUST NOT appear more than once in the same variant's recipe.

#### Scenario: Add a recipe line
- **WHEN** an authorized user adds an ingredient with a positive quantity to a variant's recipe
- **THEN** the system persists the recipe item and returns 201 with the created line

#### Scenario: Reject duplicate ingredient in a recipe
- **WHEN** a user adds an ingredient that is already part of that variant's recipe
- **THEN** the system responds with a conflict error
- **AND** no duplicate line is created

#### Scenario: Reject non-positive quantity
- **WHEN** a user adds or updates a recipe line with a quantity of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown variant, ingredient or unit
- **WHEN** a user adds a recipe line whose `product_variant_id`, `ingredient_id` or `unit_of_measure_id` does not exist in scope
- **THEN** the system responds 404 Not Found identifying the missing reference

### Requirement: View and edit a variant's recipe

The system SHALL allow authorized users to list all ingredient lines of a product variant's recipe, to update a line's quantity or unit, and to remove a line.

#### Scenario: List a variant's recipe
- **WHEN** an authorized user lists the recipe of a product variant
- **THEN** the system returns all recipe lines for that variant within the tenant

#### Scenario: Update a recipe line
- **WHEN** an authorized user updates the quantity of an existing recipe line to a positive value
- **THEN** the line is updated and returned

#### Scenario: Remove a recipe line
- **WHEN** an authorized user removes an existing recipe line
- **THEN** the line is deleted and no longer appears in the variant's recipe

### Requirement: RBAC protection of recipes endpoints

The system SHALL require the `recipes.read` permission for recipes read endpoints and the `recipes.manage` permission for recipes write endpoints. These permissions SHALL be present in the permissions catalog.

#### Scenario: Read without permission
- **WHEN** a user lacking `recipes.read` calls a recipes read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `recipes.manage` calls a recipes write endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
