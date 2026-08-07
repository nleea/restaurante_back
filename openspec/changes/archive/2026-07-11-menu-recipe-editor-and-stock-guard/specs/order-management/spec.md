## ADDED Requirements

### Requirement: Reject order items for variants without a recipe

As a safety net behind the activation guard, the system SHALL reject adding an
order item whose product variant has no recipe items, so a sale can never be
recorded for something that would not deduct inventory. This is normally
unreachable because only variants with a recipe can be activated (sold), but it
guarantees the invariant even if an active variant lost its recipe.

#### Scenario: Reject adding an item for a variant with no recipe
- **WHEN** a user adds an order item whose variant has no recipe items
- **THEN** the system responds with a validation error indicating the product has no recipe
- **AND** no order item is created

#### Scenario: Add an item for a variant that has a recipe
- **WHEN** a user adds an order item whose variant has at least one recipe item
- **THEN** the item is added as today
