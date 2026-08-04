## ADDED Requirements

### Requirement: A prepayment delivery needs a final quote before kitchen release
For a delivery order whose selected payment method requires prepayment, the system SHALL refuse
payment verification or kitchen release until the delivery has an in-coverage finalized quote.
Payment verification SHALL register the order's then-current outstanding amount, including its
frozen delivery fee, and SHALL retain the existing atomic payment-and-kitchen behavior.

#### Scenario: Verify a quoted prepaid delivery
- **WHEN** staff verify a customer's payment claim for a quoted delivery with a transfer method
- **THEN** the registered payment covers the order total including delivery fee and the order is
  routed to kitchen atomically

#### Scenario: Refuse payment before quote
- **WHEN** staff attempt to verify payment for a prepayment delivery that is pending quote or
  outside coverage
- **THEN** the action is refused and neither payment nor kitchen routing occurs
