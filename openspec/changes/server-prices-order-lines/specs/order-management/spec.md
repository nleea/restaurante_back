## MODIFIED Requirements

### Requirement: Manage order items

The system SHALL allow authorized users to add, update the quantity of, and remove items
on an open order. Each added item MAY carry an optional free-text **kitchen note** (e.g.
"sin lechuga"), set at add time and bounded in length; the note has no price or inventory
effect. Adding an item is still rejected when the variant has no recipe (the inventory
safety-net). Each item read SHALL expose whether it has been **sent to the kitchen**
(`sent` — true once it has at least one kitchen ticket).

Adding an item SHALL NOT accept a price from the caller. The request carries the variant, the
quantity and the optional note, and nothing about money. The system resolves the price itself (see
"The system owns the price of an order line").

A caller-supplied price is refused as an input, not merely ignored: while a `unit_price` field may be
tolerated for one release so an older client keeps working, the value SHALL have no effect on what is
charged.

#### Scenario: Add an item with a kitchen note

- **WHEN** an authorized user adds an item with a note
- **THEN** the item is created with that note and the note is returned on the item read

#### Scenario: Adding an item does not take a price

- **WHEN** an item is added
- **THEN** the request contains no price, and the stored unit price is the one the system resolved

#### Scenario: A price sent by an old client changes nothing

- **WHEN** a request arrives carrying a `unit_price` field
- **THEN** the item is charged at the system-resolved price, not the one sent

#### Scenario: Item is pending until routed

- **WHEN** an item has just been added
- **THEN** its `sent` flag is false and no kitchen ticket exists for it yet

#### Scenario: Item is sent once routed

- **WHEN** the order is routed to the kitchen
- **THEN** the item's `sent` flag is true

## ADDED Requirements

### Requirement: The system owns the price of an order line

The price of an order line SHALL be resolved by the system, in exactly one place, as the product's
price **for the order's branch** plus the variant's surcharge (`extra_price`). Every path that can
create an order line — staff, public storefront, customer self-service — SHALL go through that one
resolution and SHALL NOT compute or pass a price of its own.

One place is the requirement, not an implementation preference. Three callers each resolving the price
produced three different formulas: the staff client added the variant surcharge, the public path did
not, and the write path accepted whatever arrived. A single resolution is what makes those three
incapable of diverging.

The resolved price SHALL be **stamped on the line** when it is created and SHALL NOT be recomputed
afterwards. An order written yesterday keeps yesterday's price; a later price change never alters a
line already sold.

#### Scenario: The branch price plus the variant surcharge

- **WHEN** a line is added for a variant whose product costs 25000 in that branch and whose surcharge
  is 5000
- **THEN** the line's unit price is 30000

#### Scenario: The price comes from the order's branch, not another

- **WHEN** the same product has different prices in two branches and a line is added to an order of
  the second
- **THEN** the second branch's price is used

#### Scenario: Every channel charges the same

- **WHEN** the same variant is added by staff, by the public storefront and by a customer editing
  their own order
- **THEN** all three lines carry the same unit price

#### Scenario: A price change does not rewrite a sold line

- **WHEN** a product's branch price changes after a line was added
- **THEN** the existing line keeps the price it was stamped with, and the order's total does not move

#### Scenario: A new line after a price change uses the new price

- **WHEN** a line is added after the price changed
- **THEN** that line carries the new price, alongside older lines carrying the old one

### Requirement: A product with no price in the branch cannot be sold

When the product of the requested variant has no price for the order's branch, the system SHALL refuse
to create the line and SHALL say what is missing. It SHALL NOT fall back to a price of zero.

This is the same safety-net as the recipe check that already guards this boundary, one line further
down: a variant with no recipe is refused because it "would not deduct stock", and a product with no
price is refused because it would be given away. A silent zero on the money path is a gift nobody
authorised, and it is invisible until the shift is counted.

#### Scenario: No price for that branch is refused

- **WHEN** a line is added for a product with no price configured for the order's branch
- **THEN** the request is refused with a message naming the missing price, and no line is created

#### Scenario: The refusal does not leak into a zero

- **WHEN** the price lookup finds nothing
- **THEN** nothing is created at any price — in particular not at zero

#### Scenario: A price in another branch does not count

- **WHEN** the product is priced in branch A and the order belongs to branch B
- **THEN** the line is refused

### Requirement: An order line reads with its own labels

Every order item read SHALL carry the name of its product and the name of its variant, resolved by the
system. A client SHALL NOT need the menu to know what a line says.

Those names are **derived in the response**, not stored on the line. Renaming a product changes what a
live order reads, which is what is wanted, and there is no second copy of the name that can go stale.
This is deliberately different from the price, which *is* stamped: the price is money and must not
move, the label is not.

#### Scenario: A line names its product and variant

- **WHEN** an order's items are read
- **THEN** each item carries its product name and its variant name

#### Scenario: Reading lines does not need the menu

- **WHEN** a client reads an order's items without having read any menu endpoint
- **THEN** it can display every line completely

#### Scenario: A renamed product shows its new name

- **WHEN** a product is renamed while an order holding it is open
- **THEN** the order's line reads with the new name, and its price is unchanged

### Requirement: An order list can bring its items

`GET /orders` SHALL accept a request to include each order's items in the response, so that rendering
a floor with N open orders is one request rather than N.

The inclusion SHALL be opt-in and SHALL be limited to items alone. Every field callers receive today
SHALL keep its meaning and value; the items key SHALL be absent or null when it was not asked for.

Not asking SHALL cost nothing: no query for items is issued, so a caller that only needs orders pays
exactly what it paid before.

Scope is part of the requirement: this is one key, not a general expansion mechanism. An endpoint that
grows a menu of includes ends up with a different shape per screen, which is the thing a single
resource is supposed to prevent.

When items are included, they SHALL be fetched for **all** the listed orders together. Turning one
request into N queries would move the fan-out from the network to the database rather than removing it.

#### Scenario: Items arrive with the orders

- **WHEN** the orders of a branch are listed asking for items
- **THEN** each order carries its items, each with its labels and its stamped price

#### Scenario: Not asking costs nothing

- **WHEN** the orders are listed without asking for items
- **THEN** every field of the previous response is unchanged and no items are read

#### Scenario: Including items is not a database fan-out

- **WHEN** twelve orders are listed asking for items
- **THEN** their items are read together, not once per order

#### Scenario: One request instead of N

- **WHEN** a branch has twelve open orders and a client needs all their items
- **THEN** one request suffices
