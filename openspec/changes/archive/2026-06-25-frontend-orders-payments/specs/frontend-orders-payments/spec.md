## ADDED Requirements

### Requirement: Payment service layer

The Orders API service SHALL expose typed functions to register and list payments for an order,
mapping to `POST /orders/{order_id}/payments` and `GET /orders/{order_id}/payments`.

#### Scenario: Register a payment

- **WHEN** `registerPayment(orderId, { amount, method, employee_id, diner_reference? })` is called
- **THEN** it POSTs to `/orders/{orderId}/payments` and resolves with the created
  `OrderPayment` (including the server-assigned `id`, `cash_session_id`, and `branch_id`)

#### Scenario: List payments

- **WHEN** `listPayments(orderId)` is called
- **THEN** it GETs `/orders/{orderId}/payments` and resolves with the array of `OrderPayment`
  for that order

### Requirement: Payments state and derived balance

The orders store SHALL hold the payments registered for each order and expose derived getters
`paidOf(orderId)` and `balanceOf(orderId)`, where `paid = Σ payment.amount` and
`balance = order.total − paid`. Registering a payment SHALL be write-through: after the POST
succeeds the store SHALL refetch the order's payments and the order header so server-computed
totals and the payment list are shown verbatim.

#### Scenario: Balance reflects registered payments

- **WHEN** an order with `total = 50000` has one payment of `20000` loaded
- **THEN** `paidOf(order.id)` is `20000` and `balanceOf(order.id)` is `30000`

#### Scenario: Write-through refetch after registering

- **WHEN** `registerPayment` succeeds for an order
- **THEN** the store refetches that order's payments and header so `paidOf` / `balanceOf`
  reflect the new payment without a manual reload

#### Scenario: Fully settled order

- **WHEN** the sum of an order's payments equals or exceeds its `total`
- **THEN** `balanceOf(order.id)` is `0` (never negative)

### Requirement: Payment panel in the order ticket

The `OrderTicket` SHALL present a payment panel showing the order total, amount paid, and
outstanding balance; a payment method selector offering Efectivo, Nequi, Daviplata, Tarjeta and
Transferencia; an amount input prefilled with the outstanding balance; an optional diner
reference field; and the list of payments already registered for the order.

#### Scenario: Panel summarizes amounts

- **WHEN** the ticket for an open order is shown
- **THEN** the panel displays the order total, the paid amount, the outstanding balance, and the
  list of registered payments (method, amount, and diner reference when present)

#### Scenario: Amount prefilled with balance

- **WHEN** the payment form is shown for an order with a positive balance
- **THEN** the amount input is prefilled with the outstanding balance, and the cashier may edit
  it before submitting

#### Scenario: Register a payment from the panel

- **WHEN** the cashier picks a method, confirms an amount greater than zero, and submits
- **THEN** the store registers the payment and the panel updates the paid amount, balance, and
  payment list

### Requirement: Permission gating for payments

The payment panel's registration controls SHALL be shown only when the current user has the
`orders.pay` permission; users without it SHALL still see the read-only payment summary and list.

#### Scenario: Cashier with orders.pay can register

- **WHEN** the current user has `orders.pay`
- **THEN** the method selector, amount input, and "Registrar pago" action are enabled

#### Scenario: User without orders.pay sees read-only

- **WHEN** the current user lacks `orders.pay`
- **THEN** the registration controls are hidden and only the total/paid/balance summary and the
  payment list are shown

### Requirement: No open cash session is surfaced clearly

The panel SHALL detect when registering a payment fails because the branch has no open cash
session (the backend responds `409 Conflict`) and MUST show an actionable message directing the
user to open a cash session, rather than a generic error, while leaving the form values intact
for retry.

#### Scenario: Payment rejected without an open session

- **WHEN** `registerPayment` fails with a `409` conflict
- **THEN** the panel shows a message stating there is no open cash session in the branch and that
  one must be opened before charging, and keeps the entered amount and method for retry

### Requirement: Settlement guides order closing

The panel SHALL guide closing only after settlement: when the outstanding balance is greater than
zero, the "Cerrar comanda" action SHALL be discouraged with a warning that a balance remains;
when the balance reaches zero, closing SHALL be presented as the next step.

#### Scenario: Closing discouraged with an outstanding balance

- **WHEN** the order has an outstanding balance greater than zero
- **THEN** the panel warns that a balance remains before the order is closed

#### Scenario: Closing offered once settled

- **WHEN** the outstanding balance is zero
- **THEN** the panel presents closing the order as the next step
