## ADDED Requirements

### Requirement: One WhatsApp session per branch

The system SHALL hold at most one WhatsApp session per branch, identified by a provider
instance reference, with status `disconnected`, `qr_pending`, `connected` or `banned`. A
session SHALL store the provider instance reference, its status, the paired phone number once
known, and the time it was last seen. It SHALL NOT store provider authentication credentials.

#### Scenario: A branch has at most one session

- **WHEN** a session is created for a branch that already has one
- **THEN** the system rejects the creation rather than creating a second session

#### Scenario: Pairing moves the session through the lifecycle

- **WHEN** pairing is started for a branch's session
- **THEN** its status becomes `qr_pending`, and becomes `connected` once the provider reports
  the number is paired

#### Scenario: Credentials are never persisted

- **WHEN** a session is stored or read
- **THEN** no provider authentication material is present in the record

#### Scenario: Sessions are branch-scoped

- **WHEN** sessions are listed for a tenant
- **THEN** each session is anchored to exactly one branch, and a user sees only sessions of
  branches within their tenant

### Requirement: Inbound webhook persists messages scoped to the receiving branch

`POST /webhooks/whatsapp/{instance_ref}` SHALL accept inbound message notifications from the
bridge, authenticated by a shared secret. It SHALL resolve the tenant and branch from the
session matching `{instance_ref}`, find-or-create the `whatsapp_contact` by phone within the
tenant, attach the message to the contact's open conversation on that branch (creating one
when none is open), and persist the message with `sender_type = contact`. Requests whose
secret does not match SHALL be rejected without persisting anything.

#### Scenario: An inbound message lands on the right branch

- **WHEN** the bridge delivers a message to the instance paired to the `centro` branch
- **THEN** the stored conversation and message carry that branch, not the tenant's primary
  branch

#### Scenario: A new contact is created once and reused

- **WHEN** two messages arrive from the same phone number within a tenant
- **THEN** both link to the same `whatsapp_contact`, created on the first message

#### Scenario: Unknown instance reference is rejected

- **WHEN** the webhook is called with an instance reference matching no session
- **THEN** the system rejects the request and persists nothing

#### Scenario: Wrong secret is rejected

- **WHEN** the webhook is called without the shared secret or with a wrong one
- **THEN** the system rejects the request and persists nothing

#### Scenario: Unsupported message types are placeheld

- **WHEN** an inbound message is an image, audio, or location rather than text
- **THEN** a message is stored marking the unsupported type so the thread stays coherent, and
  the conversation is still surfaced to staff

### Requirement: Inbound delivery is idempotent

Each inbound message SHALL carry the provider's message identifier, unique per tenant. A
redelivered notification SHALL NOT create a second message, a second conversation, or a second
realtime notification, and the webhook SHALL respond successfully so the bridge stops retrying.

#### Scenario: Redelivery stores one message

- **WHEN** the bridge delivers the same provider message identifier three times
- **THEN** exactly one message exists in the thread

#### Scenario: Redelivery is answered successfully

- **WHEN** a duplicate notification is received
- **THEN** the system responds successfully rather than with an error that would cause
  further retries

### Requirement: Outbound is only ever a reply

The outbound gateway SHALL refuse to send a message to any phone number that has no
`whatsapp_contact` with at least one inbound message. This SHALL be enforced inside the
gateway, so that every current and future caller is bound by it without performing its own
check. The system SHALL NOT initiate a conversation with anyone.

#### Scenario: Replying to a contact who wrote is allowed

- **WHEN** a message is sent to a contact who has at least one inbound message
- **THEN** the gateway sends it

#### Scenario: Messaging a phone that never wrote is refused

- **WHEN** a send is attempted to a phone number with no contact record, or to a contact with
  no inbound message
- **THEN** the gateway refuses and no message is transmitted

#### Scenario: The guarantee does not depend on the caller

- **WHEN** any code path obtains the gateway from the composition root and attempts an
  unsolicited send
- **THEN** it is refused, because only the guarded gateway is ever injected

### Requirement: Outbound messages are persisted before transmission and reconciled

Every outbound message SHALL be written to the thread before it is handed to the bridge, with
a delivery state of `pending`. On success the state SHALL become `sent` and the provider's
message identifier SHALL be stored; on failure the state SHALL become `failed`. A failed
message SHALL remain visible in the thread.

#### Scenario: A reply that lands is marked sent

- **WHEN** an agent's reply is accepted by the bridge
- **THEN** the message is stored with delivery state `sent` and the provider's identifier

#### Scenario: A reply that fails stays visible

- **WHEN** the bridge is unreachable or rejects the send
- **THEN** the message remains in the thread marked `failed`, so the agent can see it did not
  land

### Requirement: Conversation lifecycle

A conversation SHALL have status `new`, `human` or `closed`. An inbound message SHALL join the
contact's open (`new` or `human`) conversation on that branch, or open a new one when none
exists. A conversation SHALL be closed explicitly by an agent, or treated as closed after a
configured idle window of silence.

#### Scenario: Consecutive messages share a conversation

- **WHEN** a contact sends two messages minutes apart to the same branch
- **THEN** both belong to the same conversation

#### Scenario: A message after the idle window starts a new conversation

- **WHEN** a contact writes again after the configured idle window has passed
- **THEN** a new conversation is opened and the previous one is closed

#### Scenario: The same contact on two branches has two conversations

- **WHEN** one phone number writes to two different branches of the same tenant
- **THEN** there is one contact and two conversations, one per branch

### Requirement: Shared inbox with atomic claiming

Staff SHALL be able to list the open conversations of a branch, read a thread, claim a
conversation, reply, and close it. Claiming SHALL be atomic: exactly one employee can claim a
given unclaimed conversation, and a losing attempt SHALL be told the conversation is already
taken and by whom.

#### Scenario: Two employees claim at once, one wins

- **WHEN** two employees claim the same unclaimed conversation simultaneously
- **THEN** exactly one succeeds, and the other is told it is already taken and by whom

#### Scenario: Claiming assigns and marks the conversation human

- **WHEN** an employee claims a conversation
- **THEN** the conversation carries that employee and its status becomes `human`

#### Scenario: Replies are attributed

- **WHEN** an employee sends a reply
- **THEN** the message is stored with `sender_type = employee` and that employee's identifier

#### Scenario: Closing ends the conversation

- **WHEN** an employee closes a conversation
- **THEN** its status becomes `closed` and it leaves the open list

### Requirement: Inbox updates in real time

An inbound message SHALL publish a change notification on the realtime channel, scoped to the
tenant and the receiving branch, so open inboxes refetch. Publishing SHALL be best-effort: a
broker outage SHALL NOT fail the webhook or lose the message.

#### Scenario: An open inbox learns about a new message

- **WHEN** a message arrives for a branch
- **THEN** a notification is published for that tenant and branch

#### Scenario: A broker outage does not lose messages

- **WHEN** the realtime broker is unavailable while a message arrives
- **THEN** the message is still persisted and the webhook still responds successfully

### Requirement: Permission gating

Reading the inbox SHALL require `messaging.read`. Claiming, replying and closing SHALL require
`messaging.attend`. Managing sessions (pairing, listing) SHALL require `messaging.manage`. The
inbound webhook is authenticated by its shared secret and SHALL NOT require a user permission.

#### Scenario: Read without permission

- **WHEN** a user lacking `messaging.read` calls an inbox read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Attend without permission

- **WHEN** a user lacking `messaging.attend` tries to claim, reply or close
- **THEN** the system responds 403 Forbidden

#### Scenario: Reading does not grant answering

- **WHEN** a user has `messaging.read` but not `messaging.attend`
- **THEN** they can list and read threads but every claim, reply and close is refused

#### Scenario: Session management without permission

- **WHEN** a user lacking `messaging.manage` tries to pair or list sessions
- **THEN** the system responds 403 Forbidden
