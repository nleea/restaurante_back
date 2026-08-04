## ADDED Requirements

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
