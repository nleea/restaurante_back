# frontend-kitchen (delta)

## MODIFIED Requirements

### Requirement: Cook-facing ticket board

The cook-facing board SHALL render each ticket for a station and, when the item was
ordered with a kitchen **note** (e.g. "sin lechuga"), SHALL display that note prominently
on the item row so the cook cannot miss it and does not prepare something that was not
ordered. The note is shown as plain text.

#### Scenario: Ticket shows the ordering note

- **WHEN** a ticket's item carries a kitchen note
- **THEN** the note is rendered prominently on that item row (e.g. "⚠ SIN LECHUGA")

#### Scenario: No note, no clutter

- **WHEN** a ticket's item has no note
- **THEN** no note element is rendered for it
