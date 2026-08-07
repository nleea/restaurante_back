## ADDED Requirements

### Requirement: Greeting settings screen

The front SHALL expose a per-tenant WhatsApp automation settings screen, gated on
`messaging.manage`, where the greeting can be enabled or disabled and its open and closed
variants edited. The editor SHALL list the available placeholders and SHALL show a live
preview rendered for a chosen branch, in both its open and closed forms.

#### Scenario: Editing the greeting

- **WHEN** a user with `messaging.manage` edits the greeting text and saves
- **THEN** subsequent greetings use the new text

#### Scenario: Preview shows both variants

- **WHEN** the editor is open with a branch selected
- **THEN** the open and closed renderings are both shown, with that branch's link and next
  opening substituted

#### Scenario: Unknown placeholder is rejected

- **WHEN** the text uses a placeholder that does not exist
- **THEN** saving is refused with a clear message naming the offending placeholder

#### Scenario: Disabling the greeting

- **WHEN** the greeting is disabled
- **THEN** the screen makes clear that new conversations will wait for a human

### Requirement: Status message mapping editor

The screen SHALL let the tenant choose which order and delivery transitions send a customer
message, and edit each message's text. It SHALL indicate how many messages a typical order
will produce under the current mapping, and SHALL warn when that count grows beyond the
recommended default.

#### Scenario: Opting into a transition

- **WHEN** the tenant enables the kitchen `ready` transition
- **THEN** subsequent ready events message the customer

#### Scenario: Message count is visible

- **WHEN** the mapping is edited
- **THEN** the screen shows how many messages a typical order will now send

#### Scenario: Chatty mapping is warned about

- **WHEN** the tenant enables enough transitions to exceed the recommended count
- **THEN** the screen warns that high outbound volume risks the WhatsApp number

### Requirement: Conversation and token settings

The screen SHALL expose the conversation idle window and the store token lifetime, explaining
that the idle window is what decides when a returning customer is greeted again.

#### Scenario: Editing the idle window

- **WHEN** the idle window is changed and saved
- **THEN** conversations close and re-greet on the new window

#### Scenario: Editing the token lifetime

- **WHEN** the token lifetime is changed and saved
- **THEN** newly minted store links carry the new lifetime

### Requirement: Assistant offer toggle reflects entitlement

The screen SHALL let the tenant choose whether the greeting offers the conversational
assistant, and SHALL disable that toggle with an explanation when the tenant has no assistant
enabled — so the greeting can never advertise something that will not answer.

#### Scenario: Toggle unavailable without the assistant

- **WHEN** the tenant has no assistant enabled
- **THEN** the offer toggle is disabled and explains why

#### Scenario: Toggle available with the assistant

- **WHEN** the tenant has the assistant enabled
- **THEN** the offer can be turned on and the preview shows the offer line

### Requirement: Permission gating and navigation

The settings screen SHALL require `messaging.manage`, SHALL be hidden from navigation without
it, and SHALL refuse direct entry.

#### Scenario: Hidden without permission

- **WHEN** a user without `messaging.manage` is signed in
- **THEN** the settings entry is absent from navigation and direct entry is refused
