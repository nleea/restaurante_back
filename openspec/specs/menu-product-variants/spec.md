# menu-product-variants

## Purpose

The backend surface for a product's **sellable variants** (the SKUs an order item references). It
exposes listing, creation, update, and deletion of `product_variants` for a product, and a derived
`extra_price` per variant (the sum of its composed variant options' `extra_price`, `0` for a plain
variant). The price contract for clients (orders) is: a variant's unit price = the product's
active-branch price plus the variant's `extra_price`. All endpoints are tenant-scoped; reads
require `menu.read`, writes `menu.manage`.
## Requirements
### Requirement: List a product's sellable variants

The system SHALL expose `GET /menu/products/{product_id}/variants` (gated by `menu.read`) that returns the product's sellable variants. Each variant SHALL include `id`, `product_id`, `name`, `is_active`, and a derived `extra_price` equal to the sum of the `extra_price` of its composed variant options (`0` when the variant has no composed options). The endpoint SHALL be tenant-scoped and SHALL return only variants of the given product.

#### Scenario: Lists variants with derived extra price

- **WHEN** a user with `menu.read` requests a product's variants
- **THEN** the system returns each variant with `id`, `product_id`, `name`, `is_active`, and an `extra_price` equal to the sum of its options' `extra_price` (`0` if none)

#### Scenario: Scoped to the product

- **WHEN** the product has variants and other products also have variants
- **THEN** only the requested product's variants are returned

### Requirement: Create a sellable variant

The system SHALL expose `POST /menu/products/{product_id}/variants` (gated by `menu.manage`) that creates a sellable variant for the product. The request MAY carry a `name` and MAY carry a list of `variant_option_ids` to compose. When option ids are supplied, the system SHALL validate that each belongs to a variant group of that product, rejecting otherwise. A variant created with no options SHALL have an `extra_price` of `0` and is the plain orderable unit of the product.

#### Scenario: Create a plain variant

- **WHEN** a user with `menu.manage` creates a variant with a name and no options
- **THEN** the system responds `201` with the new variant, `is_active = true` and `extra_price = 0`

#### Scenario: Create a composed variant

- **WHEN** the request includes `variant_option_ids` that belong to the product's variant groups
- **THEN** the variant is created composed of those options and its `extra_price` equals their summed `extra_price`

#### Scenario: Reject foreign options

- **WHEN** a supplied `variant_option_id` does not belong to the product's variant groups
- **THEN** the system rejects the request and creates no variant

### Requirement: Update and delete a sellable variant

The system SHALL expose `PATCH /menu/variants/{variant_id}` (gated by `menu.manage`) to rename or activate/deactivate a variant, and `DELETE /menu/variants/{variant_id}` (gated by `menu.manage`) to remove it. Both SHALL be tenant-scoped.

#### Scenario: Rename a variant

- **WHEN** a user with `menu.manage` patches a variant's `name`
- **THEN** the variant's name is updated and returned

#### Scenario: Deactivate a variant

- **WHEN** a user patches `is_active = false`
- **THEN** the variant is marked inactive

#### Scenario: Delete a variant

- **WHEN** a user with `menu.manage` deletes a variant
- **THEN** the variant is removed and no longer listed for the product

### Requirement: A recipe is required to sell a variant

The system SHALL NOT allow a product variant to become sellable (`is_active = true`)
unless it has at least one recipe item. Newly created variants SHALL default to
inactive. Deactivating a variant is always allowed and never requires a recipe.

#### Scenario: Reject activating a variant with no recipe
- **WHEN** an authorized user sets a variant `is_active = true` and the variant has no recipe items
- **THEN** the system responds with a validation error naming that a recipe is required
- **AND** the variant remains inactive

#### Scenario: Activate a variant that has a recipe
- **WHEN** a user activates a variant that has at least one recipe item
- **THEN** the variant becomes active and sellable

#### Scenario: New variant is inactive by default
- **WHEN** a variant is created
- **THEN** it is not sellable until it has a recipe and is explicitly activated

#### Scenario: Deactivation needs no recipe
- **WHEN** a user deactivates a variant
- **THEN** the variant becomes inactive regardless of whether it has a recipe

