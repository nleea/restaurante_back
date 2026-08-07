## ADDED Requirements

### Requirement: Deliveries listing scoped to the open cash session

The live deliveries listing (the dispatch board's source) SHALL return only deliveries whose order belongs to the branch's currently open cash session. Deliveries whose order has no session (`cash_session_id` null) or belongs to a closed session SHALL be excluded from the live list. Deliveries inherit their session from their order; they do not carry their own `cash_session_id`.

#### Scenario: Only the open shift's deliveries are listed

- **WHEN** the deliveries list is requested for a branch with an open cash session
- **THEN** only deliveries whose order belongs to that open session are returned

#### Scenario: Old deliveries are excluded

- **WHEN** a delivery's order belongs to a closed session or has no session
- **THEN** that delivery does not appear in the live deliveries list

#### Scenario: No open session yields an empty live list

- **WHEN** the deliveries list is requested for a branch with no open cash session
- **THEN** the live list is empty
