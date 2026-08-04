## ADDED Requirements

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
