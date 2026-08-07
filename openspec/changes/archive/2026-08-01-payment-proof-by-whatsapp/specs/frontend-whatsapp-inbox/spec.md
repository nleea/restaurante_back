## ADDED Requirements

### Requirement: An inbound file can be used as a payment receipt

On a thread message carrying an image or a PDF, the inbox SHALL offer to use it as the payment
receipt for one of that contact's unsettled orders. The action SHALL show which orders are eligible
with their number and outstanding balance, SHALL prefill the amount with that balance and allow
editing it, and SHALL be hidden — not merely disabled — from a user who cannot register payments.

After the action, the message SHALL show that it is already attached to an order, so the same file
is not attached twice by someone who did not know it had been done.

#### Scenario: Using a receipt from the thread

- **WHEN** an employee who may register payments opens the action on an image and confirms it for an
  order
- **THEN** the claim is created for that order with that file, and the order's screen shows it
  pending

#### Scenario: The eligible orders are named

- **WHEN** the action is opened
- **THEN** it lists that contact's unsettled orders with their number and balance, with the amount
  prefilled from the chosen one

#### Scenario: No unsettled order, no action

- **WHEN** the contact has no unsettled order
- **THEN** the action is not offered, and the reason is stated rather than shown as a dead button

#### Scenario: Hidden without the payment permission

- **WHEN** a user who may attend conversations but not register payments views the thread
- **THEN** the action is absent

#### Scenario: An already-used file says so

- **WHEN** a file has already been attached to an order as a receipt
- **THEN** the message states it, naming the order
