## ADDED Requirements

### Requirement: Charge an order against the open cash session

The system SHALL allow authorized users to register a payment for an `open` order with a positive `amount`, a payment `method`, an optional diner reference, and a charging employee that MUST belong to the tenant. The payment MUST be tied to the branch's currently `open` cash session; if the order's branch has no open session, the charge SHALL be rejected. Registering a payment SHALL persist both an order payment record and a cash movement of type `in` and concept `sale` (referencing the order) in that session, atomically.

#### Scenario: Charge an order with an open session
- **WHEN** an authorized user registers a payment for an open order whose branch has an open cash session
- **THEN** an order payment is persisted tied to that session
- **AND** a cash movement of type `in`, concept `sale`, with `reference_id` equal to the order id is persisted in the session

#### Scenario: Cash payment affects the arqueo
- **WHEN** a `cash`-method payment is registered and the session is later closed
- **THEN** the session's `expected_amount` includes that payment

#### Scenario: Non-cash payment is recorded but excluded from the drawer count
- **WHEN** a non-cash payment (e.g. card or Nequi) is registered and the session is later closed
- **THEN** the payment is recorded
- **AND** it does NOT change the session's physical-cash `expected_amount`

#### Scenario: Reject charging without an open session
- **WHEN** a user registers a payment for an order whose branch has no open cash session
- **THEN** the system responds with a conflict error
- **AND** neither an order payment nor a cash movement is created

#### Scenario: Reject charging a non-open order
- **WHEN** a user registers a payment for an order that is `closed` or `cancelled`
- **THEN** the system responds with a conflict error

#### Scenario: Reject non-positive amount
- **WHEN** a user registers a payment with an amount of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown charging employee
- **WHEN** a user registers a payment whose employee does not belong to the tenant
- **THEN** the system responds 404 Not Found

### Requirement: List an order's payments

The system SHALL allow authorized users to list all payments registered for an order, scoped to the current tenant.

#### Scenario: List payments
- **WHEN** an authorized user lists payments for an order
- **THEN** only that tenant's payments for that order are returned

### Requirement: RBAC protection of order charging

The system SHALL require the `orders.pay` permission to register a payment and `orders.read` to list payments.

#### Scenario: Charge without permission
- **WHEN** a user lacking `orders.pay` tries to register a payment
- **THEN** the system responds 403 Forbidden

#### Scenario: List payments with read permission
- **WHEN** a user holding `orders.read` lists an order's payments within their tenant
- **THEN** the system processes the request normally
