## ADDED Requirements

### Requirement: The recipe line's station wins over the ingredient's default

The suggestion SHALL group each ingredient by `COALESCE(recipe_line.station_id,
ingredient.default_station_id)`, so a dish that works an ingredient somewhere unusual is proposed
correctly instead of being corrected by hand every time.

An ingredient with neither SHALL keep being reported as unassigned.

#### Scenario: A line overrides the ingredient's default
- **WHEN** rice defaults to "Plancha" but this dish's recipe line names "Freidora"
- **THEN** the suggestion proposes "Freidora" for that dish, and other dishes using rice keep
  proposing "Plancha"

#### Scenario: No line station falls back to the default
- **WHEN** a recipe line has no `station_id`
- **THEN** the ingredient's default station is used

#### Scenario: Neither is set
- **WHEN** a line has no station and its ingredient has no default
- **THEN** the ingredient is reported as unassigned, as before

### Requirement: A suggested task names the ingredient it came from

Each suggested task SHALL carry the `ingredient_id` it was derived from alongside its label, so a
mapping saved from the suggestion can later be resolved against the ordered variant's recipe.

#### Scenario: Suggested tasks carry their ingredient
- **WHEN** the suggestion proposes a station's tasks
- **THEN** each one names the ingredient it was derived from
