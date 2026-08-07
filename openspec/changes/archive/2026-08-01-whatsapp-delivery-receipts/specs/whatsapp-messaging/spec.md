## MODIFIED Requirements

### Requirement: Outbound messages are persisted before transmission and reconciled

Every outbound message SHALL be written to the thread before it is handed to the bridge, with
a delivery state of `pending`. On success the state SHALL become `sent` and the provider's
message identifier SHALL be stored; on failure the state SHALL become `failed`. A failed
message SHALL remain visible in the thread.

A message that reached the provider SHALL further advance to `delivered` when the provider
reports it reached the recipient's device, and to `read` when the recipient opened it. A message
that never receives such a report SHALL remain `sent`.

#### Scenario: A reply that lands is marked sent

- **WHEN** an agent's reply is accepted by the bridge
- **THEN** the message is stored with delivery state `sent` and the provider's identifier

#### Scenario: A reply that fails stays visible

- **WHEN** the bridge is unreachable or rejects the send
- **THEN** the message remains in the thread marked `failed`, so the agent can see it did not
  land

#### Scenario: A delivered reply is marked delivered

- **WHEN** the provider reports that a `sent` message reached the recipient's device
- **THEN** the message's delivery state becomes `delivered`

#### Scenario: A read reply is marked read

- **WHEN** the provider reports that the recipient opened the message
- **THEN** the message's delivery state becomes `read`

## ADDED Requirements

### Requirement: Delivery state only ever moves forward

Applying a provider report SHALL advance a message only to a strictly higher state on the ordered
scale `pending`, `sent`, `delivered`, `read`, and SHALL be a no-op otherwise. Provider reports
arrive out of order, so a late lower report MUST NOT undo a higher state already recorded.
`failed` sits outside the scale and SHALL NOT be reached or left by a report.

#### Scenario: A late lower report does not downgrade

- **WHEN** a message is already `read` and a `delivered` report arrives afterwards
- **THEN** the message stays `read`

#### Scenario: A repeated report changes nothing

- **WHEN** the same report is delivered twice
- **THEN** the message's state is unchanged after the second one

#### Scenario: A skipped step is allowed

- **WHEN** a `sent` message receives a `read` report without a `delivered` report in between
- **THEN** the message becomes `read`

#### Scenario: A failed message is not revived

- **WHEN** a report arrives for a message whose state is `failed`
- **THEN** the message stays `failed`

### Requirement: Only the business's own messages carry receipts

A delivery report SHALL be applied only to messages the business sent. Reports about messages the
customer sent SHALL be ignored, and SHALL NOT create or alter any message.

#### Scenario: A report about an inbound message is ignored

- **WHEN** the provider reports a state change for a message the customer sent
- **THEN** nothing is stored or modified and the request is answered successfully

### Requirement: Delivery reports are matched by provider identifier

A delivery report SHALL be matched to a stored message by the provider's message identifier
within the tenant. A report whose identifier matches no stored message SHALL be ignored without
error and answered successfully, since the provider also reports on messages the system never
sent — such as ones typed on the phone itself.

#### Scenario: An unknown identifier is ignored

- **WHEN** a report arrives for an identifier that matches no stored message
- **THEN** no message is created or modified and the request is answered successfully

#### Scenario: A report never reaches another tenant's message

- **WHEN** two tenants hold messages and a report arrives for one instance
- **THEN** only the message belonging to that instance's tenant can be affected

### Requirement: A delivery report is never mistaken for an inbound message

The inbound webhook SHALL recognise a delivery report before attempting to read the payload as an
incoming message, so a report never appears in the thread as something the customer wrote.

#### Scenario: A report does not enter the thread

- **WHEN** a delivery report is posted to the webhook
- **THEN** the conversation gains no message and its status is unchanged

### Requirement: Pairing subscribes to delivery reports

Pairing a number SHALL register the delivery-report event alongside the events already
registered, so receipts work for every number paired from then on without further configuration.

#### Scenario: A newly paired number reports delivery

- **WHEN** a branch's number is paired
- **THEN** the provider is configured to send delivery reports to the webhook

#### Scenario: Re-pairing a connected number re-registers the events

- **WHEN** pairing runs again for a number that is already connected
- **THEN** the event subscription is registered again and the number stays connected
