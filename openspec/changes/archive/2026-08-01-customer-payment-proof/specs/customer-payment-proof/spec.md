## ADDED Requirements

### Requirement: A customer payment claim is not a payment

The system SHALL let a customer declare that they paid an order and attach a receipt. The
declaration SHALL be recorded separately from the order's payments and SHALL NOT change the
order's paid amount, its outstanding balance, its status, or its ability to reach the kitchen.

Only a staff verification SHALL register money for an order.

#### Scenario: A declaration leaves the money untouched

- **WHEN** a customer declares a payment for an order
- **THEN** the order's paid total, outstanding amount and status are exactly what they were

#### Scenario: A declaration does not open the kitchen

- **WHEN** a prepaid order with a pending declaration is routed to the kitchen
- **THEN** routing is refused for the same reason as before the declaration existed

#### Scenario: Only verification registers money

- **WHEN** staff verify the payment of an order that has a pending declaration
- **THEN** a payment for the order's outstanding amount is registered
- **AND** it is the verification, not the declaration, that produced it

### Requirement: A claim carries what a person needs to decide

A claim SHALL record the amount the customer says they paid, the method they used, the receipt
image, and when it was made. It SHALL belong to exactly one order.

#### Scenario: The claim shows the customer's own figures

- **WHEN** staff open an order with a pending claim
- **THEN** they see the declared amount, the method, the receipt and the time it arrived

#### Scenario: A claim belongs to one order only

- **WHEN** a claim is read
- **THEN** it is reachable only through the order it was made for

### Requirement: Claims are resolved by a person, in both directions

Staff SHALL be able to accept a claim — which happens as part of verifying the payment, from the
order screen where the kitchen is fired — or to reject it with a reason. Accepting SHALL mean a
person checked that the money actually arrived; the system SHALL NOT confirm a payment on its own. A resolved claim SHALL record who resolved it and when.

Rejecting SHALL NOT register any money and SHALL leave the customer able to send another claim.

#### Scenario: Verifying accepts the pending claims

- **WHEN** staff verify the payment of an order that has pending claims
- **THEN** those claims are marked accepted and attributed to the verifying employee

#### Scenario: Rejecting costs nothing and reopens the door

- **WHEN** staff reject a claim with a reason
- **THEN** no payment is registered
- **AND** the customer may submit a new claim for that order

#### Scenario: Verification does not require a claim

- **WHEN** staff verify a payment for an order with no claim at all
- **THEN** verification succeeds exactly as it did before this capability existed

### Requirement: The customer learns the outcome

The system SHALL notify the customer when a claim is accepted or rejected, whenever the order has
a reachable customer channel. A rejection SHALL carry the reason.

#### Scenario: An accepted claim is confirmed

- **WHEN** a claim is accepted
- **THEN** the customer is told their payment was confirmed

#### Scenario: A rejected claim says why

- **WHEN** a claim is rejected with a reason
- **THEN** the customer is told, with that reason, and can send another receipt

#### Scenario: No channel, no failure

- **WHEN** the order has no reachable customer channel
- **THEN** the claim is still resolved and nothing is sent

### Requirement: Pending claims are bounded per order

The system SHALL limit how many unresolved claims an order may hold and SHALL refuse further
declarations beyond that limit until a person resolves the pending ones.

#### Scenario: The limit is reached

- **WHEN** a customer submits more claims than the limit allows on the same order
- **THEN** the extra submission is refused and the existing claims are untouched
