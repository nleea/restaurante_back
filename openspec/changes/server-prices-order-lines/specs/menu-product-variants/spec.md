## ADDED Requirements

### Requirement: What can be ordered in a branch reads in one request

The system SHALL expose a read that returns, for one branch and in a single request, every product
that can be ordered there together with its orderable variants and **the price each variant will be
charged at**.

It SHALL be limited to what is genuinely sellable: an active product, priced for that branch, with at
least one active variant. A product the sale boundary would refuse SHALL NOT appear.

Offering an unorderable product is worse than omitting it: the tile is refused the moment somebody
taps it, in front of a customer, and the person tapping has no way to know why.

Each variant's price SHALL arrive already composed — the branch price plus the variant's surcharge —
and SHALL equal what adding that variant to an order charges. A client SHALL NOT need to compose it.
Two formulas for the same number is the defect this resolution exists to prevent, and a tile that
says one number while the line charges another is discovered when the customer reads the bill.

The read SHALL be served with **grouped queries**, not one per product. This is the point of the
read, not an optimisation of it: the screen it serves previously issued one request for products, one
per product for prices and one per product for variants.

Reading it SHALL require `menu.read`.

#### Scenario: A priced product with an active variant is orderable

- **WHEN** the orderable products of a branch are read and a product is active, priced there and has
  an active variant
- **THEN** it appears with that variant

#### Scenario: A product with no price in that branch does not appear

- **WHEN** a product has no active price for that branch
- **THEN** it is absent from the read, because adding it would be refused

#### Scenario: A price in another branch does not make it orderable

- **WHEN** a product is priced in branch A and the orderable products of branch B are read
- **THEN** it is absent from B and present in A

#### Scenario: Withdrawing a price withdraws the product

- **WHEN** a product's price for that branch is deactivated
- **THEN** it stops appearing, which is what withdrawing a price is expected to do

#### Scenario: A product with no active variant does not appear

- **WHEN** every variant of a priced product is inactive
- **THEN** the product is absent: there is nothing to order

#### Scenario: The price shown is the price charged

- **WHEN** a variant is read from this endpoint and then added to an order of that branch
- **THEN** the line's unit price equals the price the read reported

#### Scenario: The whole catalogue is one request

- **WHEN** a branch has forty orderable products
- **THEN** one request returns all of them with their variants and prices

#### Scenario: Reading requires the menu read permission

- **WHEN** a user without `menu.read` reads it
- **THEN** the request is refused
