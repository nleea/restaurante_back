## MODIFIED Requirements

### Requirement: Close an order

The system SHALL allow authorized users to close an `open` order only when it is
settled: the sum of the order's payments MUST be greater than or equal to the
order `total`, UNLESS the order has a registered customer, in which case the
unpaid remainder MAY be closed on credit. On close the system stamps `closed_at`,
sets status `closed`, and frees any associated dining table. Cash overpayment
(payments summing above `total`) is permitted and treated as change. When the
order is underpaid and has no registered customer, the system SHALL reject the
close and leave the order `open`.

#### Scenario: Close a fully paid order
- **WHEN** an authorized user closes an open order whose payments sum to at least its `total`
- **THEN** the order status becomes `closed` with `closed_at` set
- **AND** any associated table becomes `free`

#### Scenario: Overpayment is allowed as change
- **WHEN** an open order's cash payments sum to more than its `total`
- **THEN** the order closes and the excess is treated as change (no error)

#### Scenario: Reject closing an underpaid order with no customer
- **WHEN** a user closes an open order whose payments sum to less than its `total` and which has no registered customer
- **THEN** the system responds with a validation error identifying the missing amount
- **AND** the order remains `open` and no inventory is deducted

#### Scenario: Reject closing a non-open order
- **WHEN** a user closes an order that is already `closed` or `cancelled`
- **THEN** the system responds with a conflict error

## ADDED Requirements

### Requirement: Close an order on customer credit (fiado)

The system SHALL allow closing an underpaid `open` order when it has a registered
customer, recording the unpaid remainder (`total` − sum of payments) as a customer
credit for that customer, with the credit's `reference_id` set to the order and an
initial pending status. The remainder MAY be the full `total` (a fully unpaid
credit sale). No per-customer credit limit is enforced.

#### Scenario: Close with a partial payment and credit the rest
- **WHEN** an authorized user closes an open order for a registered customer whose payments cover part of the `total`
- **THEN** the order closes
- **AND** a customer credit is created for the remainder, referencing the order

#### Scenario: Fully-on-credit close
- **WHEN** an authorized user closes an open order for a registered customer with no payments registered
- **THEN** the order closes and a customer credit equal to the `total` is created for the customer

#### Scenario: Credit is settled through the existing flow
- **WHEN** a customer later pays down a credit created at order close
- **THEN** it is settled through the existing customer credit-payment flow (a cash settlement enters the open cash session)
