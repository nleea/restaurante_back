# recipes-management

## Purpose

Ingredient catalog plus per-variant Bill of Materials (BOM): the link between
sellable product variants (menu) and stock ingredients (inventory). Recipes owns
the ingredient catalog and the per-variant recipe lines; it validates variant and
unit references owned by other modules. Tenant-isolated and RBAC-protected.
## Requirements
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

### Requirement: Recipe details per variant

The system SHALL store optional recipe details per product variant — an ordered list of
preparation steps, a list of allergens restricted to `gluten|dairy|nuts|shellfish|vegan`, and an
optional photo label — at most one details row per variant. Authorized users SHALL be able to
upsert and read a variant's details; writes SHALL validate the allergen keys and reject unknown
values. The endpoints SHALL follow the module's existing permission codes (read for GET, update
for writes) and tenant isolation.

#### Scenario: Upsert details for a variant

- **WHEN** an authorized user puts steps and allergens for a variant
- **THEN** the details are stored (replacing any previous row for that variant) and returned by
  a subsequent GET

#### Scenario: Unknown allergen is rejected

- **WHEN** a write includes an allergen key outside the allowed set
- **THEN** the request fails validation and nothing is stored

#### Scenario: Variant without details

- **WHEN** a variant has no details row
- **THEN** GET details responds not-found without error noise

### Requirement: Recipe card read model

The system SHALL expose an aggregated recipe card per product variant for kitchen screens:
the variant's BOM lines with ingredient names, quantities and unit names resolved server-side,
plus the variant's steps, allergens and photo label. The card SHALL be readable with the
module's read permission in a single request. A variant with a BOM but no details SHALL return a
card with empty steps/allergens; a variant with details but no BOM SHALL return a card with an
empty ingredients list; a variant with neither SHALL respond not-found.

#### Scenario: Card aggregates BOM and details

- **WHEN** an authorized user requests the card of a variant that has BOM lines and details
- **THEN** one response carries ingredients (name, quantity, unit), steps, allergens and photo
  label — no follow-up calls needed

#### Scenario: Card with BOM only

- **WHEN** the variant has BOM lines but no details row
- **THEN** the card returns the ingredients and empty steps/allergens

#### Scenario: Card for an unknown variant

- **WHEN** the variant has neither BOM lines nor details
- **THEN** the endpoint responds not-found

### Requirement: Protect the last recipe item of an active variant

The system SHALL reject deleting the last remaining recipe item of a variant that
is currently active (sellable), so an active variant can never be left with no
recipe. Deleting recipe items from an inactive variant is always allowed, as is
deleting any non-last item.

#### Scenario: Reject removing the last recipe line while active
- **WHEN** a user deletes the only remaining recipe item of an `is_active` variant
- **THEN** the system responds with a validation error indicating the variant must be deactivated first
- **AND** the recipe item is not deleted

#### Scenario: Remove the last recipe line when inactive
- **WHEN** a user deletes the only remaining recipe item of an inactive variant
- **THEN** the item is deleted

#### Scenario: Remove a non-last recipe line
- **WHEN** a user deletes a recipe item and other items remain on the variant
- **THEN** the item is deleted regardless of the variant's active state

### Requirement: List sellable variants missing a recipe

The system SHALL expose a read of active (sellable) product variants that have no
recipe items, so the UI can flag and list variants that would sell without
deducting inventory.

#### Scenario: Report variants without a recipe
- **WHEN** an authorized user requests the sellable variants missing a recipe
- **THEN** the system returns the active variants that have zero recipe items

