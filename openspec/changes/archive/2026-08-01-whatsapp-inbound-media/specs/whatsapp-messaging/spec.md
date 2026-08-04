## ADDED Requirements

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

## MODIFIED Requirements

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
