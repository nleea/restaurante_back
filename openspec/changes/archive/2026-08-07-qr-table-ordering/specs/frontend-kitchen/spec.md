## ADDED Requirements

### Requirement: A table ticket says its table, its diner and that nobody vetted it

A kitchen ticket for a `dine_in` order SHALL show its table number, and its diner name when the
order carries one. A ticket whose order has `origin` `qr` SHALL additionally carry a mark saying so.

The table and the name are what the food is delivered by: without a waiter, whoever carries the
plate out has only the ticket to know where it goes and whose it is. The `qr` mark is a different
statement — it says no member of staff looked at this order before it reached the stove, which is
the one thing a cook should know about it and cannot infer from anything else on the ticket.

The mark SHALL follow the board's existing mono treatment for tags. Colour on this board is reserved
for heat and state, and an order's provenance is neither.

#### Scenario: A table ticket carries where and whose
- **WHEN** a ticket belongs to a `dine_in` order on table 5 placed by "Ana"
- **THEN** the ticket shows table 5 and "Ana"

#### Scenario: A QR ticket is marked
- **WHEN** a ticket belongs to an order with `origin` `qr`
- **THEN** it carries a mark identifying it as self-ordered, rendered as a mono tag

#### Scenario: A waiter's ticket is not marked
- **WHEN** a ticket belongs to a `dine_in` order opened by staff
- **THEN** it shows the table but carries no self-ordered mark

#### Scenario: Rounds read as separate tickets
- **WHEN** a diner's second round is routed
- **THEN** it appears as its own ticket, aged from its own routing time, alongside the first
