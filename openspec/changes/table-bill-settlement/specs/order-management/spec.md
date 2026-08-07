## MODIFIED Requirements

### Requirement: Record receipt prints

The system SHALL allow authorized users to record a receipt print for either an order or a table
bill — exactly one of the two — marking whether it is the first print or a reprint, attributed to an
employee.

The question the record answers ("has this been printed already, is this a reprint?") is identical
for a single comanda and for a table's bill, so it is answered by one table. Two tables for one
question drift apart.

A bill's print SHALL NOT be recorded as a print of each member order. Doing so would mark
`is_reprint` on comandas that were never printed on their own, turning an honest audit trail into
noise.

#### Scenario: Record a first print for an order
- **WHEN** an authorized user records a print for an order that has none
- **THEN** a receipt-print record is created with `is_reprint` false

#### Scenario: Record a reprint for an order
- **WHEN** an authorized user records a print for an order that already has one
- **THEN** a receipt-print record is created with `is_reprint` true

#### Scenario: Record a print for a table bill
- **WHEN** an authorized user records a print for a table bill that has none
- **THEN** a receipt-print record is created against the bill with `is_reprint` false

#### Scenario: A bill print leaves its members unprinted
- **WHEN** a bill's receipt is printed and afterwards a member order is printed on its own
- **THEN** that order's print is recorded as a first print

#### Scenario: Reject a print bound to both or neither
- **WHEN** a receipt print is recorded referencing both an order and a bill, or neither
- **THEN** the system rejects it and records nothing
