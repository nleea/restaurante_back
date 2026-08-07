## ADDED Requirements

### Requirement: Recipe editor per variant

The product detail SHALL provide a recipe (BOM) editor for the selected product
variant that lists the variant's recipe lines (ingredient, quantity, unit) and
lets an authorized user add, edit, and delete lines. Adding a line SHALL let the
user search an existing ingredient from the inventory directory or create a new
ingredient inline, enter a quantity, and use the ingredient's own unit (no unit
conversion). The editor SHALL show what selling one unit deducts.

#### Scenario: View and edit a variant's recipe
- **WHEN** an authorized user opens a product variant with recipe lines
- **THEN** the editor lists each ingredient with its quantity and unit, and offers add/edit/delete

#### Scenario: Add an ingredient to the recipe
- **WHEN** the user adds a line choosing an ingredient and a positive quantity
- **THEN** the line is saved to the variant's recipe and appears in the list, its unit taken from the ingredient

#### Scenario: Create an ingredient inline
- **WHEN** the needed ingredient does not exist and the user creates it from the editor
- **THEN** the ingredient is created and immediately usable in a recipe line without leaving the editor

### Requirement: One-click 1:1 product recipe

The product detail SHALL offer a "Producto 1:1" action for simple sellable items
(e.g. canned drinks) that, in one step, ensures an ingredient named after the
product exists (with the base unit) and adds a single recipe line of quantity 1 to
the selected variant.

#### Scenario: Make a canned drink deductible in one click
- **WHEN** the user triggers "Producto 1:1" on a variant with no recipe
- **THEN** an ingredient named after the product exists and the variant has one recipe line of quantity 1, making it deductible and activatable

### Requirement: Cannot sell a variant without a recipe

The menu UI SHALL prevent putting a variant on sale (activating it) while it has no
recipe: the activate control is disabled with an explanation, and any server-side
rejection is surfaced. Sellable variants missing a recipe SHALL be visibly flagged
and listed so they can be fixed.

#### Scenario: Activation blocked without a recipe
- **WHEN** a user tries to activate a variant that has no recipe line
- **THEN** the action is prevented and the UI explains a recipe is required before selling

#### Scenario: Missing-recipe variants are surfaced
- **WHEN** active variants exist with no recipe
- **THEN** the UI flags them ("sin receta") and offers a list so they can be corrected
