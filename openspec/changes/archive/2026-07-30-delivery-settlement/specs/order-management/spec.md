## ADDED Requirements

### Requirement: Close an unpaid order as a write-off

The system SHALL support closing an underpaid order by absorbing the unpaid remainder as a
business loss instead of charging it to the customer. A write-off close SHALL deduct inventory
through recipes exactly like any other close, SHALL mark the order closed, and SHALL NOT create a
customer credit.

This mode SHALL be reachable **only** from resolving an undelivered delivery. It SHALL NOT be
exposed as a general way to close an order: closing without payment is precisely what once made
sales vanish from the register, and the ordinary rule — pay in full or charge it to a registered
customer — SHALL remain in force for every other close.

The loss SHALL be derivable without a dedicated record: a closed order whose delivery is
`not_delivered` and whose payments fall short of its total **is** the write-off.

#### Scenario: An undelivered unpaid order closes without charging the customer

- **WHEN** a delivery of an unpaid cash order for a registered customer is marked not delivered
- **THEN** the order closes
- **AND** no customer credit is created
- **AND** the customer owes nothing for it

#### Scenario: A write-off still deducts what was cooked

- **WHEN** an order is closed as a write-off
- **THEN** its ingredients are deducted through recipes, because the food was prepared

#### Scenario: The write-off is identifiable afterwards

- **WHEN** a closed order whose delivery is `not_delivered` is inspected
- **THEN** the shortfall between its total and its payments is reported as an absorbed loss

#### Scenario: Write-off is not available to ordinary closes

- **WHEN** a user closes an underpaid order from the counter with no undelivered delivery behind it
- **THEN** the existing rules apply unchanged: the close is refused, or the remainder becomes a
  customer credit

#### Scenario: An already-paid undelivered order closes with no shortfall

- **WHEN** a delivery of a fully prepaid order is marked not delivered
- **THEN** the order closes with no remainder to absorb, and its refund is handled separately
