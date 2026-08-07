## MODIFIED Requirements

### Requirement: Order totals and discount
The system SHALL keep an order's `subtotal` equal to the sum of its item line subtotals and SHALL
keep `total` equal to `subtotal − discount + delivery_fee`. `delivery_fee` SHALL be zero for a
non-delivery order and for a delivery without a finalized quote; it SHALL be the frozen quoted fee
for a quoted delivery and SHALL NOT be derived anew from a currently configured tariff plan.
The system SHALL allow setting an order-level `discount` that MUST be at least zero and at most
the current subtotal.

#### Scenario: Item totals remain authoritative
- **WHEN** an order's active items sum to a value and it has no delivery fee
- **THEN** its `subtotal` equals the sum of line subtotals and its `total` equals subtotal minus
  discount

#### Scenario: A quoted delivery contributes to total
- **WHEN** a delivery quote freezes a fee on an order
- **THEN** its `subtotal` remains the sum of items and its `total` becomes subtotal minus discount
  plus the frozen delivery fee

#### Scenario: Reject a discount above subtotal
- **WHEN** a user sets a discount greater than the subtotal or below zero
- **THEN** the system rejects the discount without changing the delivery fee or total

## ADDED Requirements

### Requirement: Delivery orders can await a quote before payment selection
The system SHALL permit a delivery order to exist with no payment-method intent while its delivery
quote is pending. The order SHALL expose that it awaits a quote and SHALL not be represented to a
customer as having a final payable total until a delivery fee is finalized.

#### Scenario: New delivery order has no chosen method
- **WHEN** a public customer submits products and a delivery location
- **THEN** the order is created without a payment method and is marked pending quote rather than
  requiring a provisional payment choice
