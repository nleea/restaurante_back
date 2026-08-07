## ADDED Requirements

### Requirement: Dispatch board reflects the open cash session

The dispatch board SHALL show only the deliveries the backend returns for the branch's open cash session, and SHALL present a clear "caja cerrada" empty state when there is no open session (instead of a blank or misleading empty board).

#### Scenario: Board shows only the current shift

- **WHEN** the dispatcher opens the board for a branch with an open cash session
- **THEN** only that session's deliveries are shown, not older ones

#### Scenario: Closed-caja state

- **WHEN** the dispatcher opens the board for a branch with no open cash session
- **THEN** the board shows a "caja cerrada" state making clear no shift is active
