## ADDED Requirements

### Requirement: A self-service edit is priced by the system, never by the link

Every line a customer adds or changes through their edit link SHALL be priced by the system's single
resolution — the product's branch price plus the variant's surcharge — and the amount owed SHALL be
computed from those prices.

This capability already refused to take prices from the customer, and said so: *"Se resuelve TODO
contra el catálogo antes de escribir nada. El precio nunca viene del cliente."* What changes is who
does the lookup: not this use case on its own, but the one resolution every channel shares. Doing it
here was already right and still produced a divergence, because the staff channel did it differently.

A change of product on an existing line SHALL re-price that line through the same resolution, and the
difference SHALL be reflected in the amount owed.

#### Scenario: An added line is priced by the catalogue

- **WHEN** a customer adds a product through their link
- **THEN** the line carries the branch price plus the variant surcharge, and the amount owed grows by
  that much

#### Scenario: The same amount a staff member would charge

- **WHEN** a customer adds a variant with a surcharge
- **THEN** the line's price equals what the Salón would charge for the same variant in that branch

#### Scenario: Swapping a product re-prices the line

- **WHEN** a customer swaps a line's product for a more expensive one
- **THEN** the line is re-priced and the amount owed grows by the difference

### Requirement: An unpriced product cannot enter a self-service edit

The system SHALL refuse a self-service edit whose product has no price for the order's branch, and
SHALL write nothing. It SHALL NOT add that product at a price of zero.

Falling back to zero was the previous behaviour on this path, and on a customer-facing link it is the
worst place for it: a customer could add a mispriced product to their own order and owe nothing for it,
with no staff member in the loop to notice.

#### Scenario: An unpriced addition is refused

- **WHEN** a customer adds a product that has no price for that branch
- **THEN** the edit is refused, the order is untouched, and nothing was added for free

#### Scenario: The refusal keeps the order intact

- **WHEN** one line of a multi-line edit is unpriced
- **THEN** the whole edit is refused and none of its lines are written, as with any other refusal on
  this path
