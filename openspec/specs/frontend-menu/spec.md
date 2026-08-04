# frontend-menu

## Purpose

The Menu management screen — the frontend client for the backend `/menu` API. It lets an authorized
user browse and manage categories, products, per-branch prices, and addons following the mobile-first
master–detail pattern, scoped to the active branch. The screen is reached only with `menu.read`, and
mutating controls are additionally gated by `menu.manage`; this gating is UX — the backend enforces
authorization independently.
## Requirements
### Requirement: Menu route is permission-gated

The system SHALL serve the redesigned menu screen at the `/menu` route, requiring authentication and
the `menu.read` permission. The route MUST be reachable from the authenticated app navigation only
when the current user holds `menu.read`. The retired legacy menu path (`/carta`) SHALL redirect to
`/menu`.

#### Scenario: User without menu.read is blocked

- **WHEN** an authenticated user lacking `menu.read` navigates to `/menu`
- **THEN** the router redirects to the `forbidden` (`/403`) route and no menu data is fetched

#### Scenario: User with menu.read reaches the screen

- **WHEN** an authenticated user holding `menu.read` navigates to `/menu`
- **THEN** the redesigned Menu screen renders and loads categories and products for the active branch

#### Scenario: Legacy path redirects

- **WHEN** an authenticated user navigates to the retired legacy menu path (`/carta`)
- **THEN** they are redirected to `/menu`

### Requirement: Browse categories and products in master–detail

The Menu screen SHALL present categories and products following the mobile-first master–detail
pattern: on `< lg` a list fills the screen and selecting a row drills into a full-screen detail with
a back affordance; on `>= lg` both panes show at once and selection updates the detail in place.

#### Scenario: List products filtered by category

- **WHEN** the user selects a category
- **THEN** the product list shows only products whose `category_id` matches that category

#### Scenario: Toggle inactive visibility

- **WHEN** the user enables the "show inactive" filter
- **THEN** products and categories with `is_active = false` are included in the lists

#### Scenario: Drill into a product on mobile

- **WHEN** the viewport is `< lg` and the user taps a product row
- **THEN** the detail view fills the screen and a back affordance returns to the list

### Requirement: Manage categories

The system SHALL allow a user with `menu.manage` to create, edit, and delete categories, including
an optional parent (`parent_id`) for hierarchy. Users with only `menu.read` MUST see read-only views
with no mutation controls.

#### Scenario: Create a category

- **WHEN** a user with `menu.manage` submits a new category name
- **THEN** the client `POST`s to `/menu/categories` and the new category appears in the list

#### Scenario: Delete a category with dependents

- **WHEN** the user deletes a category and the backend responds `409 Conflict`
- **THEN** the UI surfaces a non-destructive conflict message explaining dependents block deletion,
  and the category remains in the list

#### Scenario: Read-only user sees no mutation controls

- **WHEN** a user holding only `menu.read` views categories
- **THEN** create, edit, and delete controls are not rendered

### Requirement: Manage products

The system SHALL allow a user with `menu.manage` to create and edit products (`name`, optional
`description`, optional `image_url`, `category_id`) and to retire a product via `is_active` rather
than forcing deletion.

#### Scenario: Create a product

- **WHEN** a user with `menu.manage` submits a product with a name and category
- **THEN** the client `POST`s to `/menu/products` and the product appears under its category

#### Scenario: Retire a product

- **WHEN** the user sets a product inactive
- **THEN** the client `PATCH`es `{ "is_active": false }` and the product is hidden unless the
  "show inactive" filter is on

#### Scenario: Delete blocked by dependents

- **WHEN** the user deletes a product and the backend responds `409 Conflict`
- **THEN** the UI surfaces a conflict message and the product remains

### Requirement: Manage per-branch prices

The system SHALL allow a user with `menu.manage` to set a product's sale price for the active branch
via an upsert, scoped to the current branch. Prices are branch-scoped: editing the active branch's
price MUST NOT affect other branches.

#### Scenario: Set a price for the active branch

- **WHEN** the user enters a price for a product in the active branch
- **THEN** the client `PUT`s to `/menu/products/{product_id}/prices/{branch_id}` with the active
  `branch_id` and the displayed price updates

#### Scenario: Price isolation across branches

- **WHEN** a price is set for the active branch
- **THEN** no request is made for any other branch and other branches' prices are unchanged

### Requirement: Manage addons and product associations

The system SHALL allow a user with `menu.manage` to maintain a catalog of addons (`name`, `price`,
`is_active`) and to attach or detach addons to a product. Attaching MUST be idempotent.

#### Scenario: Create an addon

- **WHEN** a user with `menu.manage` submits an addon name and price
- **THEN** the client `POST`s to `/menu/addons` and the addon appears in the addon catalog

#### Scenario: Attach an addon to a product

- **WHEN** the user attaches an addon to a product
- **THEN** the client calls `POST /menu/products/{product_id}/addons/{addon_id}` and the addon
  appears in the product's available addons

#### Scenario: Detach an addon from a product

- **WHEN** the user detaches an addon from a product
- **THEN** the client calls `DELETE /menu/products/{product_id}/addons/{addon_id}` and the addon is
  removed from the product's available addons

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

### Requirement: Menu editing happens in a full-screen product editor

The menu screen SHALL present product editing as a full-screen editor in which a product's identity (name, description, image, category), its per-branch price, its variants with their recipes, and its additions are all editable in one place. Categories and additions SHALL each have their own management surface within the same screen. Category marks SHALL be rendered as a mono two-letter tag derived from the category name (no dedicated backend field).

#### Scenario: Edit a product end to end

- **WHEN** an authorized user opens a product in the editor
- **THEN** they can edit its name, description, image and category, set its active-branch price, add/edit/remove variants and their recipe lines, and attach/detach additions — writing through the menu and recipes APIs

#### Scenario: Category shows a derived mono tag

- **WHEN** a category is displayed
- **THEN** its tag is the first two letters of its name, upper-cased, shown as a mono mark (not a colored dot)

#### Scenario: Read-only user sees no mutation controls

- **WHEN** a user holding only `menu.read` opens the menu screen
- **THEN** create, edit, delete, price and activation controls are not rendered

### Requirement: Live food-cost meter while editing a recipe

While a user edits a variant's recipe, the screen SHALL display a food-cost meter that updates live: the variant's recipe cost (Σ line quantity × ingredient unit cost), its margin, and its food-cost % against the active-branch price, colored by an economic-health band (good / watch / bad). When any ingredient's unit cost is unavailable, the meter SHALL show a partial/"sin costo" state and SHALL NOT present a fabricated margin.

#### Scenario: Meter updates as recipe lines change

- **WHEN** a user adds, edits or removes a recipe line on a costed variant
- **THEN** the meter's cost, margin and food-cost % recompute immediately from real ingredient unit costs and the active-branch price
- **AND** the health band reflects the new food-cost %

#### Scenario: Honest partial when cost is unavailable

- **WHEN** a variant's recipe includes an ingredient whose unit cost is unavailable
- **THEN** the meter shows a partial / "sin costo" state
- **AND** it does not display a margin computed as if that cost were zero

