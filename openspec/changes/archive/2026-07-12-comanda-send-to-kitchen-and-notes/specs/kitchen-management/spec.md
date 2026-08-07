# kitchen-management (delta)

## MODIFIED Requirements

### Requirement: KDS board and ticket lifecycle

The KDS board SHALL list a station's tickets and advance them through their lifecycle. A
ticket read SHALL expose the ordering **note** captured on its order item (e.g. "sin
lechuga"), when present, so the cook sees any special instruction. The note is read-only
on the ticket (it belongs to the order item); all of an item's station tickets carry the
same note.

#### Scenario: Ticket exposes the item's note

- **WHEN** a station's tickets are listed and an item was ordered with a kitchen note
- **THEN** each of that item's tickets includes the note text

#### Scenario: No note is absent, not empty-shown

- **WHEN** an item has no kitchen note
- **THEN** its tickets report the note as absent (null)
