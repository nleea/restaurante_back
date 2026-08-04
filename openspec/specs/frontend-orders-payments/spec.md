# frontend-orders-payments

## Purpose

The cobro (payment) slice of the Comandas screen — the frontend client for the backend's order
payment endpoints, settling an open order against its branch's cash session. Inside the
`OrderTicket` it lets an authorized cashier register one or more payments (Efectivo, Nequi,
Daviplata, Tarjeta, Transferencia), see total / paid / outstanding balance, and is guided to
close the order once settled. The operating employee is resolved via `GET /staff/employees/me`;
the branch's open cash session is resolved server-side (so the client needs no `cash.read`);
order totals are always the server's recomputation while paid/balance are derived client-side
from the payments list. Registration controls are gated by `orders.pay` (UX only — the backend
enforces authorization independently); the read-only summary and list require `orders.read`.
Opening/closing cash sessions, refunds/voids, split-by-seat tendering, and receipts are out of
scope for this slice.
## Requirements
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

The order ticket SHALL gate closing on settlement, not merely inform it. Closing
SHALL be reachable through a "Cobrar y cerrar" flow that registers one or more
payments and then closes the order. The flow SHALL show the live paid amount,
outstanding balance, and cash change, and SHALL prevent closing while the balance
is positive unless the remainder is explicitly left on customer credit. A plain
close of an underpaid order without a registered customer SHALL be prevented with
a clear message (mirroring the backend rule), never silently closing an unpaid
order.

#### Scenario: Cannot close an underpaid order without a customer
- **WHEN** the order's payments do not cover its total and it has no registered customer
- **THEN** the close control is disabled or blocked with a message that the order is not settled and a customer is required to leave it on credit

#### Scenario: Close after settling
- **WHEN** the user registers payments that cover the total and confirms
- **THEN** each payment is submitted and the order is closed, and the ticket reflects the closed, settled order

### Requirement: Cobrar y cerrar with split payments and credit

Cobro SHALL live in the Comanda's payment sheet (the order ticket's payment panel is
retired). The user registers split payments per method (efectivo / tarjeta / nequi /
transferencia), the sheet shows paid / saldo / vuelto derived from the server total,
and closing follows the settlement gate. For fiado, the user assigns an **existing**
registered customer to the order (chosen from the customers directory; no inline
create) and then closes; the backend records the unpaid remainder as that customer's
credit. The chosen customer's current credit balance is shown as a reference when
picking.

#### Scenario: Register split payments then close

- **WHEN** the user registers one or more payments that together settle the order and closes it
- **THEN** the order closes and any overpayment is shown as vuelto

#### Scenario: Assign an existing customer and fiar

- **WHEN** a balance remains and the user picks an existing customer and chooses "Fiar y cerrar"
- **THEN** the client assigns the customer to the order, closes it, and the remainder becomes the customer's credit

#### Scenario: Pick surfaces the customer's current credit

- **WHEN** the user is choosing a customer to fiar
- **THEN** each candidate shows its current outstanding credit balance as a reference

#### Scenario: No inline customer creation

- **WHEN** the needed customer does not exist
- **THEN** cobro offers no inline create; a "Crear cliente" affordance routes to the Clientes view

