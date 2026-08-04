## MODIFIED Requirements

### Requirement: Register purchase payments

The system SHALL allow authorized users to register payments against a purchase order (positive
amount, method, employee) and to list a purchase order's payments. The order `payment_status` SHALL
be `paid` when the sum of payments is at least the order total, `partial` when some but less, and
`pending` when none. When the payment `method` is `cash`, the system SHALL also post a cash movement
of type `out` and concept `purchase_payment` on the open cash session of the purchase order's branch,
referencing the order, written atomically with the payment; if that branch has no open cash session
the cash payment SHALL be rejected with a conflict and neither the payment nor a cash movement SHALL
be persisted. Payments with a non-cash method do not touch any cash session.

#### Scenario: Partial then full payment
- **WHEN** an authorized user registers a payment below the order total
- **THEN** the order `payment_status` becomes `partial`
- **AND** when subsequent payments reach the total it becomes `paid`

#### Scenario: Reject non-positive payment
- **WHEN** a user registers a payment of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Cash payment posts a drawer movement
- **WHEN** a payment with method `cash` is registered against an order whose branch has an open cash
  session
- **THEN** a cash movement of type `out`, concept `purchase_payment`, referencing the order, is
  recorded on that session
- **AND** the session's expected cash decreases by the payment amount

#### Scenario: Cash payment without an open session is rejected
- **WHEN** a payment with method `cash` is registered for an order whose branch has no open cash
  session
- **THEN** the system responds with a conflict error
- **AND** neither the payment nor a cash movement is persisted

#### Scenario: Non-cash payment does not touch the drawer
- **WHEN** a payment with a non-cash method (e.g. card, transfer) is registered
- **THEN** the payment is recorded and no cash movement is created
