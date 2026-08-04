## ADDED Requirements

### Requirement: Derive a product's stations from its recipe

The system SHALL expose `GET /kitchen/products/{product_id}/station-suggestion`, which returns
the kitchen stations that the product's recipe implies, each with the itemized task list it would
owe. The suggestion SHALL be computed from the union of the `recipe_items` of **all** the
product's variants, grouping ingredients by `ingredients.default_station_id`.

The endpoint SHALL be read-only: it never creates, updates or deletes `product_stations` rows.
Routing keeps reading `product_stations` exclusively, so a suggestion that nobody confirms has
no effect on an order.

#### Scenario: Suggest stations for a product whose ingredients carry a station
- **WHEN** an authorized user requests the suggestion for a product whose variants use
  ingredients assigned to the "Parrilla" and "Fría" stations
- **THEN** the response contains one entry per distinct station, each with the station's id and
  name and a `tasks` list holding the names of that station's ingredients
- **AND** no `product_stations` row is created

#### Scenario: Union across variants, not per variant
- **WHEN** the product has a "grande" variant using an ingredient of the "Fritos" station and a
  "pequeña" variant that does not
- **THEN** "Fritos" appears in the suggestion, because the station a product needs is the union
  of what any of its variants requires

#### Scenario: Each ingredient contributes one task, without duplicates
- **WHEN** the same ingredient appears in the recipe of two variants of the product
- **THEN** it appears once in that station's `tasks` list

### Requirement: A suggested task carries the amount, not just the name

A task SHALL name the ingredient **and** the amount the recipe calls for, with its unit —
"Carne de res 300 g", not "Carne de res". The name alone does not tell the cook what to do, and
the amount is already in the recipe.

Trailing scale zeros SHALL be dropped: the column stores `300.000` because it has three decimals,
not because the pass needs them.

Because the recipe is per variant and the station is per product, an ingredient may legitimately
carry different amounts. When that happens the suggestion SHALL list every distinct amount rather
than pick one — inventing a single number would tell the cook something that is wrong half the
time, while showing both makes the decision visible for the person to resolve before saving.

#### Scenario: The amount comes from the recipe
- **WHEN** a variant's recipe calls for 300 g of "Carne de res" worked at the grill
- **THEN** the grill's suggested task reads "Carne de res 300 g"

#### Scenario: Scale zeros are dropped
- **WHEN** the stored quantity is `300.000`
- **THEN** the task reads "300 g", and a genuine decimal such as `1.500` still reads "1.5 g"

#### Scenario: Variants disagree on the amount
- **WHEN** the "Sencilla" variant uses 150 g of an ingredient and the "Doble" uses 300 g
- **THEN** the task lists both, e.g. "Carne de res 150 g / 300 g"

#### Scenario: Variants agree on the amount
- **WHEN** every variant using the ingredient calls for the same amount
- **THEN** the amount appears once, not repeated per variant

#### Scenario: Ingredients without a station are reported, not dropped
- **WHEN** some of the product's ingredients have no `default_station_id`
- **THEN** the response returns them in a separate `unassigned_ingredients` list with their ids
  and names, so the panel can say which insumos still need a station
- **AND** those ingredients do not appear inside any suggested station's `tasks`

#### Scenario: Product with no recipe at all
- **WHEN** the product has no variants with recipe items
- **THEN** the response returns an empty station list and an empty `unassigned_ingredients` list
  with a 200 status, not an error

#### Scenario: Unknown product
- **WHEN** the requested `product_id` does not exist in the tenant
- **THEN** the system responds 404 Not Found

### Requirement: The suggestion is scoped to the active branch

The suggestion SHALL only propose stations belonging to the **active branch**. Kitchen stations
are branch-scoped while ingredients are tenant-scoped, so an ingredient's default station may
belong to a different branch than the one being configured. An ingredient whose default station
belongs to another branch SHALL be reported as unassigned for this branch rather than silently
proposing a station the branch cannot use.

#### Scenario: Default station belongs to another branch
- **WHEN** an ingredient's `default_station_id` points to a station of a branch other than the
  active one
- **THEN** that station is absent from the suggested stations
- **AND** the ingredient appears in `unassigned_ingredients` with a flag marking that its default
  station lives in another branch

#### Scenario: Tenant isolation
- **WHEN** a user of tenant A requests the suggestion for a product id belonging to tenant B
- **THEN** the system responds 404 Not Found and no cross-tenant data is returned

### Requirement: Detecting drift between stored tasks and the current recipe

The stored `product_stations.tasks` are a confirmed human copy, so they SHALL NOT change when a
recipe changes. To make the divergence visible, the suggestion response SHALL include, per
suggested station, the comparison against what is currently stored for that product and station:
the tasks the recipe now implies but the saved mapping lacks, and the saved tasks the recipe no
longer implies.

#### Scenario: Recipe gained an ingredient after the mapping was saved
- **WHEN** an ingredient of the "Parrilla" station is added to the recipe after the product's
  station mapping was saved
- **THEN** the suggestion marks that ingredient's name as missing from the saved tasks
- **AND** the saved `product_stations` row is left untouched

#### Scenario: Recipe lost an ingredient after the mapping was saved
- **WHEN** an ingredient is removed from the recipe after the mapping was saved
- **THEN** the suggestion marks the corresponding saved task as no longer implied by the recipe

#### Scenario: Saved tasks that are not ingredients survive
- **WHEN** the saved tasks include a step that is not an ingredient, such as "Emplatar"
- **THEN** it is reported as no longer implied by the recipe, but it is never removed by the
  system — only a human confirming a new assignment can drop it

#### Scenario: Mapping in sync with the recipe
- **WHEN** the saved tasks match exactly what the recipe implies for that station
- **THEN** both difference lists are empty, so the panel shows no drift notice

### Requirement: RBAC protection of the suggestion endpoint

The suggestion endpoint SHALL require the same permission that already governs reading kitchen
configuration, and SHALL NOT introduce a new permission into the catalog.

#### Scenario: Caller without the kitchen permission
- **WHEN** a user lacking the kitchen configuration permission requests the suggestion
- **THEN** the system responds 403 Forbidden

#### Scenario: Unauthenticated caller
- **WHEN** an unauthenticated request hits the suggestion endpoint
- **THEN** the system responds 401 Unauthorized
