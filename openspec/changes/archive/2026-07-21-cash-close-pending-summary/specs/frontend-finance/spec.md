## ADDED Requirements

### Requirement: Arqueo close shows pending summary and force-close

The arqueo/close screen SHALL display the session's pending summary (uncollected orders, undelivered deliveries) before closing, and SHALL require an explicit "Cerrar de todos modos" confirmation when pending items exist — without blocking the close.

#### Scenario: Closing with pending items shown

- **WHEN** the user opens the arqueo/close screen for a session with pending items
- **THEN** the pending summary is shown and closing requires an explicit force-close confirmation

#### Scenario: Clean close

- **WHEN** the session has no pending items
- **THEN** the close proceeds without a force-close warning
