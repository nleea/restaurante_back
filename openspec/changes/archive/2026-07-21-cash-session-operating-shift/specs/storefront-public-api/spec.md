## ADDED Requirements

### Requirement: Public order intake rejects when the caja is closed

The public storefront order endpoint SHALL reject an order when the resolved branch has no open cash session, returning the distinct "caja cerrada" error (HTTP 409) so the customer-facing UI can show a closed state. No order is created.

#### Scenario: Customer orders while the caja is closed

- **WHEN** a customer submits a storefront order and the branch has no open cash session
- **THEN** the request is rejected with the closed-caja error (409) and no order is created

#### Scenario: Customer orders while the caja is open

- **WHEN** a customer submits a storefront order and the branch has an open cash session
- **THEN** the order is created and stamped with that session
