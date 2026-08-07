## ADDED Requirements

### Requirement: Menu route is permission-gated

The system SHALL expose a `/menu` route that requires authentication and the `menu.read`
permission. The route MUST be reachable from the authenticated app navigation only when the
current user holds `menu.read`.

#### Scenario: User without menu.read is blocked

- **WHEN** an authenticated user lacking `menu.read` navigates to `/menu`
- **THEN** the router redirects to the `forbidden` (`/403`) route and no menu data is fetched

#### Scenario: User with menu.read reaches the screen

- **WHEN** an authenticated user holding `menu.read` navigates to `/menu`
- **THEN** the Menu screen renders and loads categories and products for the active branch

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
