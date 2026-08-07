## ADDED Requirements

### Requirement: Kitchen board scoped to the open cash session

The live kitchen board SHALL show only tickets whose order belongs to the branch's currently open cash session. Tickets whose order has no session or belongs to a closed session SHALL be excluded from the live board. Tickets inherit their session from their order.

#### Scenario: Only the open shift's tickets are shown

- **WHEN** the kitchen board is loaded for a branch with an open cash session
- **THEN** only tickets whose order belongs to that open session are shown

#### Scenario: Closed-session tickets drop off

- **WHEN** the cash session that an order was created under is closed
- **THEN** that order's kitchen tickets no longer appear on the live board
