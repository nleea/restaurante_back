# frontend-menu (delta)

## ADDED Requirements

### Requirement: Menu editing happens in a full-screen product editor

The menu screen SHALL present product editing as a full-screen editor in which a
product's identity (name, description, image, category), its per-branch price, its
variants with their recipes, and its additions are all editable in one place.
Categories and additions SHALL each have their own management surface within the same
screen. Category marks SHALL be rendered as a mono two-letter tag derived from the
category name (no dedicated backend field).

#### Scenario: Edit a product end to end

- **WHEN** an authorized user opens a product in the editor
- **THEN** they can edit its name, description, image and category, set its
  active-branch price, add/edit/remove variants and their recipe lines, and
  attach/detach additions — writing through the menu and recipes APIs

#### Scenario: Category shows a derived mono tag

- **WHEN** a category is displayed
- **THEN** its tag is the first two letters of its name, upper-cased, shown as a mono
  mark (not a colored dot)

#### Scenario: Read-only user sees no mutation controls

- **WHEN** a user holding only `menu.read` opens the menu screen
- **THEN** create, edit, delete, price and activation controls are not rendered

### Requirement: Live food-cost meter while editing a recipe

While a user edits a variant's recipe, the screen SHALL display a food-cost meter
that updates live: the variant's recipe cost (Σ line quantity × ingredient unit
cost), its margin, and its food-cost % against the active-branch price, colored by an
economic-health band (good / watch / bad). When any ingredient's unit cost is
unavailable, the meter SHALL show a partial/"sin costo" state and SHALL NOT present a
fabricated margin.

#### Scenario: Meter updates as recipe lines change

- **WHEN** a user adds, edits or removes a recipe line on a costed variant
- **THEN** the meter's cost, margin and food-cost % recompute immediately from real
  ingredient unit costs and the active-branch price
- **AND** the health band reflects the new food-cost %

#### Scenario: Honest partial when cost is unavailable

- **WHEN** a variant's recipe includes an ingredient whose unit cost is unavailable
- **THEN** the meter shows a partial / "sin costo" state
- **AND** it does not display a margin computed as if that cost were zero

## MODIFIED Requirements

### Requirement: Menu route is permission-gated

The redesigned menu screen SHALL be served at the menu route and SHALL remain gated
by `menu.read`; a user without it is blocked, a user with it reaches the screen. The
retired legacy menu path SHALL redirect to the redesigned screen.

#### Scenario: User without menu.read is blocked

- **WHEN** a user lacking `menu.read` navigates to the menu route
- **THEN** they are blocked (redirected to the forbidden view) and the screen does
  not load

#### Scenario: User with menu.read reaches the screen

- **WHEN** a user holding `menu.read` navigates to the menu route
- **THEN** the redesigned menu screen loads

#### Scenario: Legacy path redirects

- **WHEN** an authorized user navigates to the retired legacy menu path
- **THEN** they are redirected to the redesigned menu screen
