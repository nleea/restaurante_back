## ADDED Requirements

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

The config SHALL carry a `dishCard` section with a card `style` of `list`, `card`, or `grid`,
and independent visibility toggles for the dish fields: image, description, price, addon hint,
and removable hint. The chosen style and toggles SHALL apply uniformly to every dish in the
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
derived from that product's variant recipe items (BOM). Deriving this list SHALL NOT modify the
recipe. Excluding an ingredient SHALL be a subtractive-only action; the preview SHALL NOT offer
any control to add or increase a recipe ingredient — additions exist only through the addons
lane.

#### Scenario: Recipe ingredients appear as removable options

- **WHEN** a previewed dish's variant has recipe items and the `remove` section is visible
- **THEN** each recipe ingredient appears as a togglable exclusion in the detail preview

#### Scenario: Excluding is subtractive only

- **WHEN** the dish-detail preview shows the removable-ingredient list
- **THEN** each ingredient offers only exclude/keep, with no quantity or add control, and the
  addons list is the only place that adds items

#### Scenario: Dish without a recipe shows no removables

- **WHEN** a previewed dish's variant has no recipe items
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

All new configuration (`dishCard`, `dishDetail`, new blocks) SHALL live in the existing
draft/published in-memory model. `publish()` SHALL copy draft to published locally, with no
network call, so the shape stays API-ready for the follow-up persistence change.

#### Scenario: Publish keeps changes local

- **WHEN** the admin publishes after editing presentation config
- **THEN** the published copy updates in memory, no API request is made, and the draft/published
  shape is unchanged in structure
