## ADDED Requirements

### Requirement: A kitchen station is required to sell a variant

The system SHALL NOT allow a product variant to become sellable (`is_active = true`) unless its
product is mapped to at least one kitchen station. Deactivating a variant is always allowed and
never requires a station. The validation error SHALL name what is missing and where it is fixed,
not merely refuse.

This is the same class of rule as the recipe requirement, for the same reason: selling something
the business cannot actually produce is a promise it cannot keep. Without a station the order is
taken, charged and closed while the kitchen never sees the item.

The station belongs to the PRODUCT while the recipe belongs to the VARIANT, so activating a
variant checks something its siblings share. That is deliberate — the product is what gets cooked;
its size does not change who prepares it.

#### Scenario: Reject activating a variant whose product has no station
- **WHEN** an authorized user sets a variant `is_active = true` and its product is mapped to no
  kitchen station
- **THEN** the system responds with a validation error naming that a kitchen station is required
- **AND** the variant remains inactive

#### Scenario: Activate a variant whose product has a station
- **WHEN** a user activates a variant whose product is mapped to at least one station and which
  has at least one recipe item
- **THEN** the variant becomes active and sellable

#### Scenario: Both conditions are required
- **WHEN** a user activates a variant whose product has a station but the variant has no recipe
- **THEN** the system still refuses, naming the recipe

#### Scenario: Deactivation needs no station
- **WHEN** a user deactivates a variant whose product has no station
- **THEN** the variant becomes inactive with no further requirement

#### Scenario: Losing its last station does not silently unsell a product
- **WHEN** the last station mapping of a product with active variants is removed
- **THEN** the system makes that product's variants identifiable as no longer sellable rather
  than leaving them active and unroutable
