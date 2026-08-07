## MODIFIED Requirements

### Requirement: A prepaid order reaches the kitchen only through payment verification

An order whose payment method is anything other than cash SHALL require its payment to be
verified before it can be routed to the kitchen. Verification is a single human action — staff
inspect the transfer receipt or the payment app and confirm — and that action SHALL both register
the payment for the order's full outstanding amount and route the order to the kitchen. The two
SHALL succeed or fail together: an order SHALL NOT reach the kitchen with the payment unregistered,
and SHALL NOT be marked paid without being routed.

A customer's payment declaration SHALL be an aid to that decision, never a substitute for it:
verification SHALL remain possible with no declaration at all, and a declaration SHALL never
route an order by itself. When verification succeeds, it SHALL resolve the order's pending
declarations as accepted.

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

#### Scenario: Verification without a declaration still works

- **WHEN** staff verify a prepaid order for which the customer never declared anything
- **THEN** verification proceeds and registers the outstanding amount

#### Scenario: Verifying accepts what the customer declared

- **WHEN** staff verify an order that has pending declarations
- **THEN** those declarations are marked accepted in the same operation

## ADDED Requirements

### Requirement: A raised total after verification is charged as the remainder

The next verification of an order that grew after being verified SHALL register only the
difference between the order's total and what has already been paid, leaving the earlier payment
untouched.

#### Scenario: Adding to a paid order leaves only the difference owed

- **WHEN** a verified order of 40.000 grows to 42.500 and is verified again
- **THEN** a payment of 2.500 is registered
- **AND** the original payment is unchanged

#### Scenario: What the customer is shown is what is missing

- **WHEN** the customer reads an order they have partly paid
- **THEN** the amount presented to them is what remains, not the order's total
