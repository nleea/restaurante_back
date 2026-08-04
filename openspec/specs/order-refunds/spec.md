# order-refunds

## Purpose

La obligación de devolver dinero de un pedido prepagado que no se entregó: cómo nace, cómo
se lista mientras nadie la resuelve, y cómo se salda contra la caja **con el método por el
que entró**.

Sólo lo prepagado genera devoluciones. El efectivo se cobra en la puerta, así que un pedido
no entregado en efectivo nunca se pagó — y como lo prepagado nunca tocó el cajón, saldarla
no mueve el arqueo.

Fuera de alcance: devoluciones parciales, y ejecutar la transferencia de vuelta (la hace un
humano; aquí sólo se garantiza que la deuda no se pierda de vista).

## Requirements
### Requirement: A prepaid order that was not delivered owes a refund

When a delivery is marked `not_delivered` and its order carries payments, the system SHALL create
a pending refund obligation for the amount already paid, recording the order it came from, the
amount, and the payment method the money arrived by. Cash orders SHALL NOT produce a refund: cash
is collected on delivery, so an undelivered order was never paid.

#### Scenario: A prepaid undelivered order creates a pending refund

- **WHEN** a delivery of an order paid by transfer is marked not delivered
- **THEN** a pending refund is created for the amount paid, carrying the `transfer` method

#### Scenario: A cash undelivered order creates no refund

- **WHEN** a delivery of an unpaid cash order is marked not delivered
- **THEN** no refund is created

#### Scenario: One refund per order

- **WHEN** an order that already has a pending refund is marked not delivered again
- **THEN** no second refund is created

### Requirement: Refunds are listed until they are resolved

The system SHALL list pending refunds for a branch, showing the order, the customer, the amount
and the method, and SHALL keep listing them until each is confirmed or cancelled. A refund SHALL
NOT disappear from the list by the passage of time or by the closing of a cash session.

#### Scenario: A pending refund stays visible across shifts

- **WHEN** a cash session with a pending refund is closed and a new one is opened
- **THEN** the refund is still listed as pending

#### Scenario: A resolved refund leaves the list

- **WHEN** a refund is confirmed or cancelled
- **THEN** it no longer appears among the pending refunds

### Requirement: Confirming a refund records the money leaving with its original method

Confirming a refund SHALL record who authorized it and when, and SHALL create a cash movement of
type `out` for the refunded amount **carrying the method the money originally arrived by**. A
refund SHALL NOT be recorded as cash unless the original payment was cash.

#### Scenario: A transfer refund does not touch the drawer

- **WHEN** an authorized user confirms a refund of a payment made by transfer
- **THEN** an `out` cash movement is created with method `transfer`
- **AND** the session's expected cash amount is unchanged

#### Scenario: Confirmation records its author

- **WHEN** an authorized user confirms a refund
- **THEN** the refund becomes `done` with the confirming employee and the time recorded

#### Scenario: A confirmed refund cannot be confirmed twice

- **WHEN** a refund that is already `done` is confirmed again
- **THEN** the system responds with a conflict error and no second movement is created

### Requirement: A refund can be cancelled with a reason

The system SHALL allow an authorized user to cancel a pending refund, recording who cancelled it
and why, for the case where the money is not returned (the customer accepted a replacement, the
order was re-sent, the charge never settled). A cancelled refund SHALL create no cash movement.

#### Scenario: Cancelling closes the obligation without moving money

- **WHEN** an authorized user cancels a pending refund with a reason
- **THEN** the refund becomes `cancelled` with the reason and its author recorded
- **AND** no cash movement is created

#### Scenario: A reason is required to cancel

- **WHEN** a user cancels a refund without a reason
- **THEN** the system responds with a validation error

### Requirement: Pending refunds never block a cash session

A pending refund SHALL NOT prevent a cash session from closing. The money left by a method other
than cash, so the drawer reconciles regardless.

#### Scenario: A session closes with refunds outstanding

- **WHEN** a session with pending refunds is closed and all its deliveries are resolved
- **THEN** the close succeeds
