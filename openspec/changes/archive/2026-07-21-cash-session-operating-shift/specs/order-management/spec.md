## ADDED Requirements

### Requirement: Orders belong to a cash session

Every order SHALL carry the `cash_session_id` of the branch's cash session that was open at the moment it was created. The value is set once at creation and is the single source of truth for which operating shift the order (and its deliveries and kitchen tickets) belongs to.

#### Scenario: Order stamped with the open session

- **WHEN** an order is created for a branch that has an open cash session
- **THEN** the order's `cash_session_id` is set to that open session's id

#### Scenario: Pre-existing orders carry no session

- **WHEN** an order created before this capability existed is read
- **THEN** its `cash_session_id` is null and it is treated as belonging to no live shift

### Requirement: Order creation requires an open cash session

Order creation SHALL be gated at the single creation choke point (`OrderService.open_order`) for every channel (dine-in/salón, storefront, delivery). If the branch has no open cash session, creation SHALL be rejected with a distinct "caja cerrada" error (HTTP 409), not a generic validation error.

#### Scenario: Creation rejected when the caja is closed

- **WHEN** any channel attempts to create an order for a branch with no open cash session
- **THEN** the request is rejected with a distinct closed-caja error (409) and no order is persisted

#### Scenario: Creation succeeds when the caja is open

- **WHEN** a channel creates an order for a branch with an open cash session
- **THEN** the order is created and stamped with that session
