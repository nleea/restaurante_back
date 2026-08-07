## ADDED Requirements

### Requirement: A ticket carries the amount of the variant that was ordered

Routing an order SHALL resolve each station task against the recipe of the **ordered variant**,
not the product. A task that carries an `ingredient_id` SHALL be emitted with that variant's
quantity for that ingredient; a task without one is free text and SHALL be emitted verbatim.

`order_item_stations.tasks` SHALL remain a plain list of strings: the ticket is a frozen, already
resolved copy that the KDS renders as-is.

#### Scenario: Two variants, two amounts
- **WHEN** the "Sencilla" variant uses 150 g of an ingredient, the "Doble" uses 300 g, and both
  are ordered
- **THEN** the Sencilla's ticket reads "Carne de res 150 g" and the Doble's reads
  "Carne de res 300 g"

#### Scenario: Hand-written steps pass through
- **WHEN** a mapping's tasks include a free-text step such as "Emplatar"
- **THEN** it appears verbatim on the ticket of every variant

#### Scenario: An ingredient the ordered variant does not use is not emitted
- **WHEN** a product-level mapping carries a task for an ingredient that the ordered variant's
  recipe does not include
- **THEN** that task is absent from that ticket, because telling the cook to add something the
  dish does not contain is worse than saying nothing

#### Scenario: Resolution never empties or breaks a ticket
- **WHEN** an ingredient's recipe line cannot be resolved for any reason
- **THEN** the task is emitted with its label and no amount, and the ticket is still created

#### Scenario: Already-fired tickets are untouched
- **WHEN** an order is routed a second time
- **THEN** existing tickets keep the tasks captured at first route

### Requirement: Amounts are shown in the kitchen's unit, not the inventory's

An amount SHALL be presented in the sub-unit of its family when it is smaller than one — `0.150 kg`
reads `150 g` — resolved from `units_of_measure.base_unit_id` and `conversion_factor`, which
already model the family. No conversion table is hard-coded.

Trailing scale zeros SHALL be dropped in every case.

#### Scenario: Sub-unit conversion under one
- **WHEN** a recipe line calls for `0.150 kg` and `g` exists as a sub-unit of `kg`
- **THEN** the task reads "150 g"

#### Scenario: One or more stays in its own unit
- **WHEN** a recipe line calls for `1.500 kg`
- **THEN** the task reads "1.5 kg", because kilos read naturally at that size

#### Scenario: A unit with no sub-unit
- **WHEN** the unit has no smaller unit in its family, e.g. `und`
- **THEN** the amount is shown in that unit unchanged, e.g. "1 und"

### Requirement: A station task remembers the ingredient it came from

`product_stations.tasks` SHALL hold, per task, a label and an optional `ingredient_id`. Derived
tasks carry the ingredient; hand-written steps do not.

Reading SHALL tolerate the previous shape — a plain list of strings — treating each entry as a
label with no ingredient, so existing mappings keep working without a backfill. Writing SHALL
accept both shapes and normalize.

#### Scenario: Old mappings keep working
- **WHEN** a mapping stored before this change holds `["Carne", "Emplatar"]`
- **THEN** it reads as two labels with no ingredient, and routing emits both verbatim

#### Scenario: A derived task keeps its ingredient through an edit
- **WHEN** a person renames a derived task's label from "Carne de res" to "Carne"
- **THEN** the task keeps its `ingredient_id`, so the amount still resolves per variant

#### Scenario: Writing the legacy shape is accepted
- **WHEN** a client sends `tasks` as a plain list of strings
- **THEN** they are stored as labels with no ingredient
