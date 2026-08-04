## ADDED Requirements

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
