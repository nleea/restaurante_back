## MODIFIED Requirements

### Requirement: Manage customers

The system SHALL allow authorized users to create a customer by capturing the person inline (a
required name plus optional document, phone, email), optionally linking a login user, and to list
(optionally by active state), retrieve, update and deactivate customers. The created `person` and
`customer` SHALL be persisted together. A linked `user`, when provided, MUST belong to the current
tenant. Customer read responses (create, list and retrieve) SHALL embed the person's identity
fields — `first_name`, `last_name`, `document_number`, `phone` and `email` — so a client can
display and search customers without a separate person lookup.

#### Scenario: Create a customer
- **WHEN** an authorized user creates a customer with a name
- **THEN** a person and an active customer are persisted and the customer is returned
- **AND** the response includes the person's `first_name`, `last_name`, and any document, phone and
  email provided

#### Scenario: Reject unknown linked user
- **WHEN** a user creates a customer linking a `user_id` not in the current tenant
- **THEN** the system responds 404 Not Found

#### Scenario: List and view customers
- **WHEN** an authorized user lists customers (optionally filtered by active) or fetches one by id
- **THEN** only the tenant's matching customers are returned
- **AND** each returned customer carries its person's identity fields (name, document, phone, email)

#### Scenario: Deactivate a customer
- **WHEN** an authorized user deactivates a customer
- **THEN** the customer's `is_active` becomes false and it remains retrievable
