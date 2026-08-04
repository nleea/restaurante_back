## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Cobrar y cerrar with split payments and credit

The order ticket SHALL provide a "Cobrar y cerrar" action that opens a settlement
panel where the user adds one or more payment lines, each with a payment method
and an amount, and sees the running paid total, outstanding balance, and cash
change. It SHALL offer a "Fiar el resto" option that is enabled ONLY when the
order has a registered customer; when on, the outstanding balance is shown as the
amount that will be left on credit. On confirm, the ticket SHALL submit each
payment line via the payments endpoint and then close the order; backend errors
(no open cash session; not settled / customer required) SHALL be surfaced inline.

#### Scenario: Split payment across methods
- **WHEN** the user adds a cash line and a Nequi line that together cover the total and confirms
- **THEN** both payments are registered and the order is closed

#### Scenario: Fiar the remainder for a registered customer
- **WHEN** the order has a registered customer, the user pays part of the total, enables "Fiar el resto", and confirms
- **THEN** the partial payment is registered, the order is closed, and the remainder is left on the customer's credit

#### Scenario: Fiar is unavailable without a registered customer
- **WHEN** the order has no registered customer
- **THEN** the "Fiar el resto" option is disabled and closing requires full payment

#### Scenario: No open cash session is surfaced
- **WHEN** submitting a payment returns a no-open-cash-session error
- **THEN** the panel shows that a cash session must be open, and the order is not closed
