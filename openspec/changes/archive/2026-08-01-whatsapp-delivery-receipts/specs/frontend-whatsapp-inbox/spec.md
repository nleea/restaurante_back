## ADDED Requirements

### Requirement: A team message shows how far it got

The thread SHALL show, on every message the team sent, whether it is still going out, reached the
provider, reached the customer's device, or was read. Messages the customer sent SHALL NOT carry
any such indicator.

#### Scenario: Delivered and read are distinguishable

- **WHEN** one team message is `delivered` and another is `read`
- **THEN** the two are visually distinct from each other and from a merely `sent` one

#### Scenario: An inbound message carries no receipt

- **WHEN** the customer's message is shown
- **THEN** no delivery indicator is rendered on it

#### Scenario: A message with no report yet reads as sent

- **WHEN** a team message has been accepted by the bridge and no report has arrived
- **THEN** it shows as sent, not as failed and not as pending

#### Scenario: Failing is still unmistakable

- **WHEN** a team message failed to send
- **THEN** it is still shown as failed, distinctly from every other state

### Requirement: The receipt is legible without colour alone

The distinction between delivery states SHALL NOT rest on colour alone: each state SHALL differ in
its mark or its accessible label, so it survives a greyscale screen and a screen reader.

#### Scenario: Each state is named for assistive technology

- **WHEN** a team message is rendered in any delivery state
- **THEN** an accessible label states that state in words

### Requirement: Numbers paired before receipts existed are called out

The sessions screen SHALL state that a number paired before delivery reports existed does not
report them until it is paired again, and that pairing again does not disconnect a connected
number.

#### Scenario: The sessions screen explains the re-pairing

- **WHEN** a user with `messaging.manage` opens the sessions screen
- **THEN** it explains that re-pairing is what turns on delivery reports for an existing number
