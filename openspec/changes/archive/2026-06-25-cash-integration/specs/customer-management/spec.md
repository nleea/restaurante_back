## MODIFIED Requirements

### Requirement: Settle credit with payments

The system SHALL allow authorized users to register payments against a customer credit (positive
amount, method, employee) and to list a credit's payments. The credit `payment_status` SHALL be
`paid` when the sum of payments is at least the credit total, `partial` when some but less, and
`pending` when none. When the payment `method` is `cash`, the system SHALL also post a cash movement
of type `in` and concept `credit_payment` on the open cash session of the paying employee's branch
(customer credits are tenant-level and carry no branch, so the branch is resolved from the employee
registering the payment), referencing the credit, written atomically with the payment; if that
branch has no open cash session the cash payment SHALL be rejected with a conflict and neither the
payment nor a cash movement SHALL be persisted. Payments with a non-cash method do not touch any cash
session.

#### Scenario: Partial then full settlement
- **WHEN** an authorized user registers a payment below the credit total
- **THEN** the credit `payment_status` becomes `partial`
- **AND** when subsequent payments reach the total it becomes `paid`

#### Scenario: Reject non-positive payment
- **WHEN** a user registers a credit payment of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Cash settlement posts a drawer movement
- **WHEN** a payment with method `cash` is registered by an employee whose branch has an open cash
  session
- **THEN** a cash movement of type `in`, concept `credit_payment`, referencing the credit, is
  recorded on that session
- **AND** the session's expected cash increases by the payment amount

#### Scenario: Cash settlement without an open session is rejected
- **WHEN** a payment with method `cash` is registered by an employee whose branch has no open cash
  session
- **THEN** the system responds with a conflict error
- **AND** neither the payment nor a cash movement is persisted

#### Scenario: Non-cash settlement does not touch the drawer
- **WHEN** a payment with a non-cash method (e.g. transfer, Nequi) is registered
- **THEN** the payment is recorded and no cash movement is created
