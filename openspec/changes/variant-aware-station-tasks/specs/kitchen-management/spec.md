## ADDED Requirements

### Requirement: Routing resolves tasks against the ordered variant's recipe

`route_order` SHALL resolve each mapping task before freezing it onto the ticket: a task carrying
an `ingredient_id` is emitted with the quantity that the **ordered variant's** recipe calls for,
and a task without one is emitted verbatim.

This resolution SHALL never prevent a ticket from being created. Routing is the critical path of
every comanda, so any failure to resolve an amount degrades to emitting the label alone.

#### Scenario: The amount comes from the ordered variant
- **WHEN** an order item for the "Doble" variant is routed
- **THEN** its ticket carries the Doble's quantities, not the product's union of amounts

#### Scenario: Degradation instead of failure
- **WHEN** an amount cannot be resolved
- **THEN** the ticket is still created and the task appears without an amount

#### Scenario: Routing stays idempotent
- **WHEN** the same order is routed twice
- **THEN** the second route creates nothing and existing tickets keep their frozen tasks
