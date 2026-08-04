# recipes-management (delta)

## ADDED Requirements

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
