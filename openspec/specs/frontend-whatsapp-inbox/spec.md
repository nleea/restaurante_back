# frontend-whatsapp-inbox

## Purpose

El inbox compartido de WhatsApp acotado a la sucursal activa: lista de conversaciones con su
estado de atención, hilo, tomar, responder y cerrar — en vivo sobre el doorbell de realtime,
con respaldo por polling.

Incluye la pantalla de números por sucursal, cuyo trabajo es que **una sucursal muda sea
imposible de pasar por alto**: hasta que exista la alerta del cambio 3, es el único sitio
donde se ve que un número dejó de recibir.

## Requirements
### Requirement: Shared inbox route

The front SHALL expose a WhatsApp inbox route showing the open conversations of the **active
branch**: for each, the contact's name or phone, the last message preview, its time, and
whether it is unclaimed or held by an employee. Conversations of other branches SHALL NOT
appear.

#### Scenario: Inbox lists the active branch's conversations

- **WHEN** a user with `messaging.read` opens the inbox with the `centro` branch active
- **THEN** only `centro` conversations are listed, each with contact, preview, time and
  claim state

#### Scenario: Switching branch switches the inbox

- **WHEN** the user changes the active branch
- **THEN** the inbox reloads with that branch's conversations

#### Scenario: Empty state

- **WHEN** the active branch has no open conversations
- **THEN** the inbox shows an empty state rather than a blank panel

### Requirement: Thread view and reply

Selecting a conversation SHALL show its full thread in order, distinguishing messages from the
contact, from employees, and from the system, and SHALL show which employee sent each staff
reply. A user with `messaging.attend` SHALL be able to write and send a reply from the thread.

A message carrying an image SHALL render the image inline, at a size that lets the agent read a
payment receipt without leaving the inbox, and SHALL open it full-size on demand. A message
carrying a PDF SHALL offer to open it. A message whose file could not be retrieved SHALL say so
rather than appearing empty or broken.

#### Scenario: Thread shows both sides

- **WHEN** a conversation with inbound and outbound messages is opened
- **THEN** the thread renders them in order, visually distinguishing who sent each

#### Scenario: Sending a reply appends it

- **WHEN** an attending employee sends a reply
- **THEN** it appears in the thread attributed to them

#### Scenario: A failed reply is visible

- **WHEN** a reply could not be delivered
- **THEN** it stays in the thread marked as failed, so the agent knows it did not land

#### Scenario: An image is readable in the thread

- **WHEN** the customer sent a photo
- **THEN** the thread renders it inline, large enough to read a receipt, and opens it full-size on
  demand

#### Scenario: A PDF is offered, not embedded

- **WHEN** the customer sent a PDF
- **THEN** the thread offers to open it

#### Scenario: A caption reads as the message

- **WHEN** the customer's photo carried a caption
- **THEN** the caption is the message text, with the image below or beside it

#### Scenario: A file that could not be retrieved says so

- **WHEN** a message arrived with a file that could not be fetched
- **THEN** the thread states that a file arrived and could not be retrieved, with no broken image

### Requirement: Claiming is explicit and conflict-aware

An unclaimed conversation SHALL be claimable from the inbox. When another employee claims it
first, the losing user SHALL be told it is already taken and by whom, and the conversation
SHALL update to show its holder rather than appearing available.

#### Scenario: Claiming shows the holder

- **WHEN** an employee claims a conversation
- **THEN** it shows as held by them, in their own inbox and in everyone else's

#### Scenario: Losing a claim is explained, not silent

- **WHEN** an employee claims a conversation another employee just took
- **THEN** they are told it is already taken and by whom, and the list updates to reflect it

#### Scenario: Closing removes it from the open list

- **WHEN** an attending employee closes a conversation
- **THEN** it leaves the open list

### Requirement: Inbox reacts to the realtime doorbell

The inbox SHALL refresh from the realtime notification when a message arrives for the active
branch, without the user reloading. When realtime is unavailable it SHALL fall back to
polling, consistent with the other live boards.

#### Scenario: A new message appears without reloading

- **WHEN** a message arrives for the active branch while the inbox is open
- **THEN** the conversation list and, if that thread is open, the thread update on their own

#### Scenario: Polling fallback

- **WHEN** the realtime channel is unavailable
- **THEN** the inbox still updates on its polling interval

### Requirement: Sessions screen

The front SHALL expose a per-branch WhatsApp session screen for users with
`messaging.manage`, showing each branch's connection status and paired number, and allowing
pairing to be started and the QR to be shown.

#### Scenario: Status per branch is visible

- **WHEN** a user with `messaging.manage` opens the sessions screen
- **THEN** each branch's session status and paired number are shown

#### Scenario: A disconnected branch is obvious

- **WHEN** one branch's session is disconnected while others are connected
- **THEN** that branch is clearly marked as not receiving messages

#### Scenario: Pairing shows the QR

- **WHEN** pairing is started for a branch
- **THEN** the QR is displayed and the status shows as awaiting pairing

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

### Requirement: Permission gating and navigation

The inbox route SHALL require `messaging.read` and the sessions route `messaging.manage`; both
SHALL be hidden from navigation and refused on direct entry without them. Claim, reply and
close controls SHALL be hidden or disabled without `messaging.attend`.

#### Scenario: Inbox hidden without read

- **WHEN** a user without `messaging.read` is signed in
- **THEN** the inbox entry is absent from navigation and direct entry is refused

#### Scenario: Read-only user cannot answer

- **WHEN** a user has `messaging.read` but not `messaging.attend`
- **THEN** they can read threads, and the claim, reply and close controls are unavailable

#### Scenario: Sessions hidden without manage

- **WHEN** a user without `messaging.manage` is signed in
- **THEN** the sessions entry is absent from navigation and direct entry is refused

### Requirement: The composer offers the tenant's quick replies

The message composer SHALL offer the tenant's quick replies through a control next to the other
composer actions, listing each entry by name with a preview of its text.

#### Scenario: The list is reachable from the composer

- **WHEN** a staff member who can attend the conversation opens the quick replies control
- **THEN** the tenant's quick replies are listed by name

#### Scenario: No quick replies configured

- **WHEN** the tenant has no quick replies
- **THEN** the control is either absent or states that none are configured, and never shows an
  empty menu with no explanation

### Requirement: Selecting a quick reply fills the composer without sending

Selecting a quick reply SHALL insert its text into the draft and return focus to the message
field. It SHALL NOT send the message: sending remains an explicit, separate action by the staff
member.

#### Scenario: Selection does not send

- **WHEN** a staff member selects a quick reply
- **THEN** the text appears in the draft, nothing is transmitted, and the send action is still
  pending

#### Scenario: Focus returns to the message field

- **WHEN** a staff member selects a quick reply
- **THEN** the message field regains focus so the text can be edited immediately

### Requirement: Inserting a quick reply never discards typed text

Insertion SHALL happen at the caret position and SHALL preserve everything the staff member has
already typed. A quick reply SHALL NOT replace, truncate, or clear the existing draft.

#### Scenario: Existing draft is preserved

- **WHEN** the draft already contains text and a quick reply is selected
- **THEN** the existing text remains and the quick reply text is inserted at the caret

#### Scenario: Two quick replies can be combined

- **WHEN** a staff member selects one quick reply and then another
- **THEN** both texts are present in the draft

### Requirement: The quick replies control follows the composer's own gates

The control SHALL be unavailable in exactly the situations where the composer already refuses to
write: no permission to attend, a closed conversation, or a disconnected WhatsApp number.

#### Scenario: Hidden without permission to attend

- **WHEN** a user can read the conversation but not attend it
- **THEN** the quick replies control is not available

#### Scenario: Hidden while the number is disconnected

- **WHEN** the WhatsApp number is disconnected
- **THEN** the quick replies control is not available, matching the composer's own refusal to
  accept a draft

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
