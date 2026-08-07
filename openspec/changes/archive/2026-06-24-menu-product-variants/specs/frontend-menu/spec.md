## ADDED Requirements

### Requirement: Manage a product's sellable variants

The menu product detail SHALL include a "Variantes vendibles" section that lists the product's sellable variants (showing each variant's name and its `extra_price`), and — gated by `menu.manage` — lets the user add a variant (a name; and, when the product has variant options available, optionally compose them) and delete a variant. The section SHALL make clear that a variant's orderable price is the product's active-branch price plus the variant's `extra_price`.

#### Scenario: List a product's variants

- **WHEN** the user opens a product's detail
- **THEN** the product's sellable variants are listed with their name and extra price

#### Scenario: Add a plain variant

- **WHEN** a user with `menu.manage` adds a variant with a name and no options
- **THEN** the variant is created and appears in the list with `extra_price` of `0`

#### Scenario: Delete a variant

- **WHEN** a user with `menu.manage` deletes a variant
- **THEN** the variant is removed from the list

#### Scenario: Read-only without manage

- **WHEN** a user without `menu.manage` views the section
- **THEN** the variants are listed but the add and delete controls are hidden
