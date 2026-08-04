# whatsapp-messaging

## Purpose

WhatsApp como canal real del producto: una sesión (un número) por sucursal, un webhook de
entrada idempotente que persiste contactos, conversaciones y mensajes con la sucursal que
los recibió, y un inbox compartido donde el personal responde.

**Contestado 100% por humanos, cero IA.** La automatización del saludo y el asistente son
cambios posteriores; esto es la fontanería que ambos necesitan validada primero.

La regla que sostiene todo lo demás: **nunca iniciamos una conversación**. Sólo se puede
escribir a quien ya nos escribió, y eso se hace cumplir dentro del gateway, no en cada
llamador — es lo que protege el número de que lo bloqueen.

Fuera de alcance: multimedia (sólo texto; lo demás se guarda como marcador), varios números
por sucursal, y un número sirviendo a varias sucursales.

## Requirements
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

The provider's own message reference SHALL be persisted in full — not only its identifier — when the
provider requires it to fetch that message's file later. Reconstructing a provider reference from a
phone number SHALL NOT be treated as equivalent: the address forms differ between providers and
accounts.

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

- **WHEN** an inbound message is a voice note, a video, a sticker or a location rather than text
- **THEN** a message is stored marking the unsupported type so the thread stays coherent, and
  the conversation is still surfaced to staff

#### Scenario: The provider reference is kept for later retrieval

- **WHEN** a media message is persisted
- **THEN** the provider reference needed to fetch its file is stored with it

### Requirement: Inbound images and PDFs are stored and readable in the thread

When an inbound message carries an image, or a document whose type is PDF, the system SHALL fetch
the file from the bridge, store it, and attach its location and type to the stored message so that
staff can see it inside the product. Files above a configured size limit SHALL be refused **without
being downloaded**, by reading the size and type the bridge reports in the notification.

Other media kinds — audio, video, stickers, locations, and documents of other types — SHALL keep
their readable text placeholder. Not supporting them is a scope decision, not an omission: the
thread SHALL stay coherent either way.

#### Scenario: An image is stored and attached to the message

- **WHEN** a customer sends a photo to the branch's number
- **THEN** the message stored in the thread carries the image's location and type, and staff can
  open it from the inbox

#### Scenario: A PDF receipt is stored

- **WHEN** a customer sends a PDF, as banks produce them
- **THEN** it is stored and attached the same way an image is

#### Scenario: An oversized file is refused before it is downloaded

- **WHEN** the bridge reports an inbound file larger than the size limit
- **THEN** no download is attempted, and the message is stored with its placeholder

#### Scenario: Unsupported kinds keep their placeholder

- **WHEN** an inbound message is a voice note, a video, a sticker or a location
- **THEN** the message is stored with the placeholder naming the kind, and no file is fetched

### Requirement: A failed media fetch never loses the message

The inbound message SHALL be persisted before any attempt to fetch its file. When the fetch or the
storage fails, the message SHALL remain in the thread stating that a file arrived and could not be
retrieved, and the failure SHALL NOT fail the webhook, the greeting, the assistant, or any other
automatic reply.

#### Scenario: The bridge cannot return the file

- **WHEN** the file cannot be fetched from the bridge
- **THEN** the message is still in the thread, marked as a file that could not be retrieved

#### Scenario: Storage is not configured

- **WHEN** file storage is not configured for the deployment
- **THEN** inbound messages behave exactly as they did before this capability, with their
  placeholders, and the reason is recorded in the log

#### Scenario: A redelivery does not fetch or store twice

- **WHEN** the bridge delivers the same media message more than once
- **THEN** exactly one message exists, one file is stored, and the duplicate causes no fetch

### Requirement: A caption is the message's content

When an inbound media message carries a caption, that caption SHALL be the stored message's
content, and the media SHALL be attached alongside it. When there is no caption, the placeholder
naming the kind SHALL be the content.

Discarding what the customer typed is the same defect as discarding the file, and it is the more
costly of the two: the caption is what tells staff what the file is.

#### Scenario: The caption is kept

- **WHEN** a customer sends a photo captioned "aquí va mi comprobante del pedido A3F2"
- **THEN** the thread shows that text as the message, with the image attached

#### Scenario: No caption keeps the placeholder

- **WHEN** a customer sends a photo with no caption
- **THEN** the message content is the placeholder naming the kind, with the image attached

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

### Requirement: Send a delivery payment request to a reachable contact

The messaging system SHALL send a message identifying the order, its final total and the secure payment link when a delivery payment request is created and the order is linked to a reachable WhatsApp contact. It SHALL record whether the emission succeeded, failed or is pending and SHALL NOT change the quote, payment or kitchen state if messaging fails.

#### Scenario: Quote emits one WhatsApp request

- **WHEN** a quoted delivery has a linked reachable WhatsApp contact
- **THEN** the system sends one payment-request message for that quote and records its emission

#### Scenario: No reachable WhatsApp contact

- **WHEN** a quoted delivery has no linked reachable WhatsApp contact
- **THEN** the quote remains valid, no unsolicited message is sent, and the payment request is surfaced for operational follow-up

### Requirement: Emission happens where the link is still readable

The system SHALL send a payment request only while its single-use token is still in clear text, because only its hash is persisted. A failed or unsent emission SHALL therefore be recovered by issuing a NEW payment request — invalidating the previous one — and never by attempting to resend the previous link.

#### Scenario: Operator recovers a failed emission

- **WHEN** an authorized user retries a payment request whose WhatsApp emission failed
- **THEN** the system issues a new single-use request for the same unchanged quote, invalidates the previous request, and sends the new link

#### Scenario: A stored request cannot be resent

- **WHEN** any code path attempts to build a payment link from a persisted request
- **THEN** no usable link can be produced, because the stored request holds only the token hash
