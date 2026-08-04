# order-management (delta)

## MODIFIED Requirements

### Requirement: Manage order items

The system SHALL allow authorized users to add, update the quantity of, and remove items
on an open order. Each added item MAY carry an optional free-text **kitchen note** (e.g.
"sin lechuga"), set at add time and bounded in length; the note has no price or inventory
effect. Adding an item is still rejected when the variant has no recipe (the inventory
safety-net). Each item read SHALL expose whether it has been **sent to the kitchen**
(`sent` — true once it has at least one kitchen ticket).

#### Scenario: Add an item with a kitchen note

- **WHEN** an authorized user adds an item with a note
- **THEN** the item is created with that note and the note is returned on the item read

#### Scenario: Item is pending until routed

- **WHEN** an item has just been added
- **THEN** its `sent` flag is false and no kitchen ticket exists for it yet

#### Scenario: Item is sent once routed

- **WHEN** the order is routed to the kitchen
- **THEN** the item's `sent` flag is true

### Requirement: Auto-route new items to the kitchen

Adding an item SHALL NOT route the order to the kitchen. Items are created *pending* and
reach the KDS only when the order is explicitly routed (the "Enviar a cocina" action, via
the kitchen route endpoint). This lets staff compose the full order before the cook
starts, and lets an un-sent order be cancelled with no kitchen impact.

#### Scenario: Adding an item does not create a kitchen ticket

- **WHEN** an authorized user adds an item to an open order
- **THEN** no kitchen ticket is created for it and the order's `kitchen_state` stays `none`

#### Scenario: Explicit routing creates the tickets

- **WHEN** the order is routed to the kitchen after items were added
- **THEN** kitchen tickets are created for the pending items and the order becomes `in_kitchen`
