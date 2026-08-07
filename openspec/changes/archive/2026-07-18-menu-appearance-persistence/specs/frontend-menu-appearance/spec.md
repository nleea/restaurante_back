## MODIFIED Requirements

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
