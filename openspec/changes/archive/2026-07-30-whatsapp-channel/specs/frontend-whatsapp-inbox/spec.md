## ADDED Requirements

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

#### Scenario: Thread shows both sides

- **WHEN** a conversation with inbound and outbound messages is opened
- **THEN** the thread renders them in order, visually distinguishing who sent each

#### Scenario: Sending a reply appends it

- **WHEN** an attending employee sends a reply
- **THEN** it appears in the thread attributed to them

#### Scenario: A failed reply is visible

- **WHEN** a reply could not be delivered
- **THEN** it stays in the thread marked as failed, so the agent knows it did not land

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
