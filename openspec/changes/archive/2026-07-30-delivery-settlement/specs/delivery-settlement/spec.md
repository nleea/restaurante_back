## ADDED Requirements

### Requirement: A prepaid order reaches the kitchen only through payment verification

An order whose payment method is anything other than cash SHALL require its payment to be
verified before it can be routed to the kitchen. Verification is a single human action — staff
inspect the transfer receipt or the payment app and confirm — and that action SHALL both register
the payment for the order's full outstanding amount and route the order to the kitchen. The two
SHALL succeed or fail together: an order SHALL NOT reach the kitchen with the payment unregistered,
and SHALL NOT be marked paid without being routed.

#### Scenario: Verifying a prepaid payment pays and fires the order

- **WHEN** an authorized user verifies the payment of an unrouted order whose method is `transfer`
- **THEN** a payment for the order's outstanding amount is registered with that method
- **AND** the order is routed to the kitchen in the same operation

#### Scenario: A cash order needs no verification

- **WHEN** an order whose payment method is `cash` is routed to the kitchen
- **THEN** routing succeeds with no payment registered

#### Scenario: Verification is refused when it cannot be completed

- **WHEN** verification is attempted and the payment cannot be registered (for example, no open
  cash session)
- **THEN** the operation is refused and the order is neither paid nor routed

#### Scenario: Verifying an already verified order does not double-charge

- **WHEN** an authorized user verifies an order whose payments already cover its total
- **THEN** no additional payment is registered and the order is routed

### Requirement: Delivering an order closes it

Marking a delivery as `delivered` SHALL close its order. Closing SHALL go through the same
order-closing rules that apply anywhere else — payments must cover the total or a registered
customer absorbs the remainder on credit, and inventory is deducted through recipes — so an
order closed by a delivery is indistinguishable from one closed at the counter.

#### Scenario: A delivered prepaid order closes on delivery

- **WHEN** a delivery of an already-paid order is marked delivered
- **THEN** its order is closed
- **AND** the order no longer appears as pending collection

#### Scenario: Closing rules are not bypassed by the delivery path

- **WHEN** a delivery of an order that is neither paid nor attached to a customer is marked
  delivered
- **THEN** the order is not closed and the caller is told what is missing

#### Scenario: A not-delivered order is also settled

- **WHEN** a delivery is marked `not_delivered`
- **THEN** its order is closed too, absorbing any unpaid remainder as a write-off rather than
  charging it to the customer

### Requirement: Resolving a delivery always settles its order

Both endings of a delivery SHALL settle the order: `delivered` closes it under the ordinary
rules, and `not_delivered` closes it as a write-off. An order behind a resolved delivery SHALL
NOT stay open.

The reason is inventory: closing is the only moment ingredients are deducted through recipes, and
the food of an undelivered order was cooked all the same. Leaving it open would keep the pantry
reporting stock that no longer exists.

#### Scenario: An undelivered order does not stay open forever

- **WHEN** a delivery is marked not delivered
- **THEN** its order is closed and stops appearing among the open orders

#### Scenario: The ingredients of an undelivered order are still deducted

- **WHEN** a delivery of a cooked order is marked not delivered
- **THEN** the order's ingredients are deducted through recipes

#### Scenario: The customer is not charged for what never arrived

- **WHEN** an unpaid delivery is marked not delivered for a registered customer
- **THEN** no customer credit is created against that customer

### Requirement: Cash is collected at the door and closes the order in one action

For an order whose payment method is cash, the system SHALL expose the amount the courier must
collect, and SHALL provide a single action that registers the cash payment and closes the order
together. Either both happen or neither does: a collected payment SHALL NOT leave the order open,
and an order SHALL NOT close without the money recorded.

#### Scenario: The courier confirms the money and the order closes

- **WHEN** the courier confirms collection for a cash delivery of a known amount
- **THEN** a cash payment for that amount is registered against the order
- **AND** the order is closed in the same operation

#### Scenario: The amount owed is visible before confirming

- **WHEN** the courier opens a cash delivery that has not been paid
- **THEN** the outstanding amount is reported

#### Scenario: A failed collection leaves the order open

- **WHEN** registering the cash payment fails
- **THEN** the order remains open and the delivery is not settled

### Requirement: Cash collected on delivery lands in the session that owns the order

A cash payment collected at the door SHALL be recorded against the open cash session of the
order's branch, exactly as a payment taken at the counter, producing the matching cash movement.

#### Scenario: Collection is recorded in the open session

- **WHEN** a courier confirms a cash collection while a session is open at the branch
- **THEN** the payment and its `sale` cash movement are recorded against that session

#### Scenario: Collection without an open session is refused

- **WHEN** a courier confirms a cash collection and no session is open at the branch
- **THEN** the collection is refused and the order stays open
