## ADDED Requirements

### Requirement: Deduct inventory on close via recipes

When an order is closed, the system SHALL deduct ingredients from inventory based on each non-cancelled item's product-variant recipe (BOM). For each recipe line of each item, the system SHALL record an inventory movement of type `out`, reason `sale`, quantity equal to `recipe_line_quantity × item_quantity`, at the order's branch, with `reference_id` equal to the order id, attributed to the order's employee, and decrement the ingredient's on-hand accordingly. Deduction SHALL occur in the same operation as the close.

Deduction SHALL be non-blocking: if an ingredient's on-hand is insufficient, the close still succeeds and the on-hand MAY become negative (signaling a recount is due). A product variant with no recipe SHALL consume nothing. Deduction SHALL be idempotent: an order that has already produced `sale` movements SHALL NOT be deducted again.

#### Scenario: Closing deducts ingredients scaled by quantity
- **WHEN** an order with an item of quantity 3, whose variant recipe uses 150 (g) of an ingredient, is closed
- **THEN** the order status becomes `closed`
- **AND** an inventory `out` movement of reason `sale`, quantity 450, referencing the order, is recorded for that ingredient at the order's branch
- **AND** the ingredient's on-hand decreases by 450

#### Scenario: Insufficient stock still closes and goes negative
- **WHEN** an order is closed and a required ingredient has less on-hand than needed
- **THEN** the close succeeds
- **AND** the ingredient's on-hand becomes negative by the shortfall

#### Scenario: Variant without a recipe consumes nothing
- **WHEN** an order whose item variant has no recipe is closed
- **THEN** the close succeeds
- **AND** no inventory movement is created for that item

#### Scenario: Cancelled items are not deducted
- **WHEN** an order with a cancelled item and an active item is closed
- **THEN** only the active item's recipe ingredients are deducted

#### Scenario: Deduction does not double-count
- **WHEN** an order has already been closed and its ingredients deducted
- **THEN** the order cannot be closed again
- **AND** no additional `sale` movements are produced for that order
