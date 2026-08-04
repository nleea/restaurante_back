## ADDED Requirements

### Requirement: Tenant isolation for customers

The system SHALL scope every customers read and write to the `tenant_id` resolved by the subdomain middleware. No request SHALL read or mutate customers, preferences or credits of another tenant.

#### Scenario: Tenant cannot see another tenant's customers
- **WHEN** a request for tenant A lists customers
- **THEN** only customers whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a customer id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a customers endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage customers

The system SHALL allow authorized users to create a customer by capturing the person inline (a required name plus optional document, phone, email), optionally linking a login user, and to list (optionally by active state), retrieve, update and deactivate customers. The created `person` and `customer` SHALL be persisted together. A linked `user`, when provided, MUST belong to the current tenant.

#### Scenario: Create a customer
- **WHEN** an authorized user creates a customer with a name
- **THEN** a person and an active customer are persisted and the customer is returned

#### Scenario: Reject unknown linked user
- **WHEN** a user creates a customer linking a `user_id` not in the current tenant
- **THEN** the system responds 404 Not Found

#### Scenario: List and view customers
- **WHEN** an authorized user lists customers (optionally filtered by active) or fetches one by id
- **THEN** only the tenant's matching customers are returned

#### Scenario: Deactivate a customer
- **WHEN** an authorized user deactivates a customer
- **THEN** the customer's `is_active` becomes false and it remains retrievable

### Requirement: Manage customer preferences

The system SHALL allow authorized users to set, list and remove free-form key/value preferences for a customer of the current tenant.

#### Scenario: Set a preference
- **WHEN** an authorized user sets a key/value preference on an existing customer
- **THEN** the preference is persisted and returned

#### Scenario: List preferences
- **WHEN** an authorized user lists a customer's preferences
- **THEN** only that customer's preferences within the tenant are returned

#### Scenario: Remove a preference
- **WHEN** an authorized user removes an existing preference
- **THEN** the preference no longer exists

### Requirement: Register store credit

The system SHALL allow authorized users to register a store credit (fiado) owed by a customer, with a positive total amount and an optional loose `reference_id`, and to list a customer's credits and retrieve one. A credit starts with `payment_status` `pending`.

#### Scenario: Register a credit
- **WHEN** an authorized user registers a credit for an existing customer with a positive amount
- **THEN** the credit is persisted with `payment_status` `pending` and returned

#### Scenario: Reject non-positive credit amount
- **WHEN** a user registers a credit with an amount of zero or less
- **THEN** the system responds with a validation error

#### Scenario: Reject credit for unknown customer
- **WHEN** a user registers a credit for a customer not in the current tenant
- **THEN** the system responds 404 Not Found

### Requirement: Settle credit with payments

The system SHALL allow authorized users to register payments against a customer credit (positive amount, method, employee) and to list a credit's payments. The credit `payment_status` SHALL be `paid` when the sum of payments is at least the credit total, `partial` when some but less, and `pending` when none.

#### Scenario: Partial then full settlement
- **WHEN** an authorized user registers a payment below the credit total
- **THEN** the credit `payment_status` becomes `partial`
- **AND** when subsequent payments reach the total it becomes `paid`

#### Scenario: Reject non-positive payment
- **WHEN** a user registers a credit payment of zero or less
- **THEN** the system responds with a validation error

### Requirement: RBAC protection of customers endpoints

The system SHALL require the `customers.read` permission for customers read endpoints and the `customers.manage` permission for all customers write endpoints (customers, preferences, credits, credit payments).

#### Scenario: Read without permission
- **WHEN** a user lacking `customers.read` calls a customers read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `customers.manage` tries to create a customer or register a credit
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
