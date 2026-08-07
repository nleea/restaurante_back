# frontend-menu-appearance

## Purpose

The admin editor for the public carta's presentation, at `/menu/appearance` (gated by
`menu.manage`). It configures the customer-facing storefront's look — theme, brand, layout blocks
(banner, featured categories, search, full menu, footer, plus promo/hours/gallery/testimonials), a
global dish-card style, and the dish-detail layout — with a live phone preview fed by the tenant's
real menu data. Presentation config is held in memory (draft/published) this phase; persistence to a
DB is a follow-up capability.

## Requirements

### Requirement: Preview renders real menu data

The appearance preview SHALL render the tenant's actual categories, products, prices, and
addons read from the menu store, not hardcoded sample content. When menu data has not loaded,
the preview SHALL show a neutral placeholder state rather than fabricated dishes.

#### Scenario: Real dishes appear in the full-menu block

- **WHEN** the menu store has loaded products and prices and the `full_menu` block is visible
- **THEN** the preview lists those products grouped by their real categories, each with its real
  name and active-branch price

#### Scenario: Featured categories reflect real categories

- **WHEN** the `featured_categories` block is visible and categories have loaded
- **THEN** the preview's category chips are the tenant's real category names, in category order

#### Scenario: Menu data not yet loaded

- **WHEN** products have not finished loading
- **THEN** the preview shows a neutral loading/empty placeholder and does not display invented
  dish names or prices

### Requirement: Global dish-card presentation is configurable

The config SHALL carry a `dishCard` section with a card `style` of `list`, `card`, `grid`, or
`hero`, and independent visibility toggles for the dish fields: image, description, price, addon
hint, and removable hint. The chosen style and toggles SHALL apply uniformly to every dish in the
preview, and SHALL be editable from a dedicated panel.

#### Scenario: Switching card style restyles all dishes

- **WHEN** the admin changes `dishCard.style` from `list` to `grid`
- **THEN** every dish in the preview re-renders in the grid layout without changing any product
  data

#### Scenario: Hiding a field removes it from every card

- **WHEN** the admin turns off `dishCard.show.description`
- **THEN** no dish card in the preview shows a description, while other fields remain

#### Scenario: Card config is part of the draft

- **WHEN** the admin edits any `dishCard` value
- **THEN** the save bar reports unsaved changes (draft differs from published) and Discard
  restores the published card config

### Requirement: Dish-detail layout is configurable

The config SHALL carry a `dishDetail` section: an ordered list of detail sections — photo,
description, variants, addons, remove (quitar ingredientes), and note — each with a visibility
flag. The admin SHALL be able to reorder and toggle these sections, and a live dish-detail
preview SHALL reflect the order and visibility in real time.

#### Scenario: Reordering sections changes the detail preview

- **WHEN** the admin moves the `addons` section above `variants`
- **THEN** the dish-detail preview renders addons before variants

#### Scenario: Hiding a section removes it from the detail

- **WHEN** the admin hides the `note` section
- **THEN** the dish-detail preview shows no free-text note field

#### Scenario: A hidden remove section hides removable ingredients

- **WHEN** the admin hides the `remove` section
- **THEN** the dish-detail preview shows no "quitar ingredientes" list even for a dish that has
  a recipe

### Requirement: Removable ingredients derive from the recipe without altering it

For a given product, the removable-ingredient list shown in the dish-detail preview SHALL be
derived from that product's variant recipe items (BOM), keeping only ingredients whose ingredient
is marked `is_customer_removable`. Deriving this list SHALL NOT modify the recipe. Excluding an
ingredient SHALL be a subtractive-only action; the preview SHALL NOT offer any control to add or
increase a recipe ingredient — additions exist only through the addons lane.

#### Scenario: Recipe ingredients appear as removable options

- **WHEN** a previewed dish's variant has recipe items whose ingredients are `is_customer_removable`
  and the `remove` section is visible
- **THEN** each such recipe ingredient appears as a togglable exclusion in the detail preview

#### Scenario: Non-removable staples are excluded

- **WHEN** a recipe item's ingredient has `is_customer_removable` false (e.g. salt, oil)
- **THEN** it does not appear in the removable-ingredient list, even though it is in the recipe

#### Scenario: Excluding is subtractive only

- **WHEN** the dish-detail preview shows the removable-ingredient list
- **THEN** each ingredient offers only exclude/keep, with no quantity or add control, and the
  addons list is the only place that adds items

#### Scenario: Dish without removable ingredients shows none

- **WHEN** a previewed dish's variant has no recipe items marked `is_customer_removable`
- **THEN** the removable-ingredient list is empty (or hidden) and the rest of the detail renders
  normally

### Requirement: Expanded layout block set

The canvas SHALL offer four additional layout blocks beyond banner/featured/search/full_menu/
footer: `promo`, `hours`, `gallery`, and `testimonials`. Each new block SHALL participate in
the same grid placement, resize, collision, and hidden-tray behavior as existing blocks, and
SHALL render in the preview. Content for `promo`, `hours`, and `testimonials` SHALL be
admin-editable and held in the config; `gallery` SHALL be able to source images from product
`image_url`s.

#### Scenario: A new block is placed on the canvas

- **WHEN** the admin drags the `promo` block from the hidden tray onto a free cell
- **THEN** it snaps to the grid, cannot overlap another block, and appears in the preview in
  linear reading order

#### Scenario: New block renders its content in the preview

- **WHEN** the `hours` block is visible with admin-entered schedule text
- **THEN** the preview renders that schedule content inside the hours block

#### Scenario: Gallery can use product photos

- **WHEN** the `gallery` block is visible and products have `image_url`s
- **THEN** the preview's gallery can display those product images

### Requirement: Presentation config persists only in memory this phase

The appearance config SHALL be loaded from and saved to the appearance API. On mount, the editor
SHALL GET the tenant's saved config (falling back to defaults when none exists) into both the
published and draft copies. `publish()` SHALL PUT the draft to the API and, on success, set it as
the published copy. `discard()` and `isDirty` keep comparing draft against the last published copy.

#### Scenario: Editor loads the saved config

- **WHEN** the appearance editor mounts for a tenant with a saved config
- **THEN** the editor shows that saved config and reports no unsaved changes

#### Scenario: Publish writes to the API

- **WHEN** the admin publishes after editing
- **THEN** the draft is PUT to the appearance API and, on success, becomes the published copy so
  isDirty returns false

#### Scenario: Missing config falls back to defaults

- **WHEN** the editor mounts for a tenant that has never saved a config
- **THEN** the editor shows the default config without error and lets the admin publish it
