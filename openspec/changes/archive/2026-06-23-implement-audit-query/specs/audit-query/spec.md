## ADDED Requirements

### Requirement: Tenant isolation for audit queries

The system SHALL scope every audit query to the `tenant_id` resolved by the subdomain middleware. No request SHALL read audit entries belonging to another tenant.

#### Scenario: Tenant cannot see another tenant's audit entries
- **WHEN** a request for tenant A lists audit entries
- **THEN** only entries whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches an audit entry id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** an audit endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Query the audit log

The system SHALL allow authorized users to list audit entries for the current tenant, ordered most-recent first, filterable by `action` (exact value or dotted prefix such as `login`), `actor_id`, `entity_type`, `entity_id`, and `branch_id`, with `limit`/`offset` pagination (a default limit and an enforced maximum). The system SHALL also allow retrieving a single audit entry by id.

#### Scenario: List recent entries
- **WHEN** an authorized user lists audit entries
- **THEN** the tenant's entries are returned newest-first, bounded by the limit

#### Scenario: Filter by action prefix
- **WHEN** an authorized user lists entries filtered by action prefix `login`
- **THEN** only entries whose action starts with `login` (e.g. `login.success`, `login.failure`) are returned

#### Scenario: Filter by actor
- **WHEN** an authorized user lists entries filtered by an `actor_id`
- **THEN** only that actor's entries within the tenant are returned

#### Scenario: Paginate
- **WHEN** an authorized user lists entries with a `limit` and `offset`
- **THEN** at most `limit` entries are returned starting at `offset`
- **AND** a limit above the maximum is clamped to the maximum

#### Scenario: Retrieve a single entry
- **WHEN** an authorized user fetches an existing audit entry id of the tenant
- **THEN** the entry is returned

### Requirement: Audit log is read-only via the API

The system SHALL NOT expose endpoints to create, update or delete audit entries. Audit entries are written only by the internal recorder and are immutable.

#### Scenario: No write endpoints
- **WHEN** the audit API surface is inspected
- **THEN** it exposes only read operations (list and get); there is no create/update/delete

### Requirement: RBAC protection of audit endpoints

The system SHALL require the `audit.read` permission for all audit query endpoints. This permission SHALL be present in the permissions catalog.

#### Scenario: Read without permission
- **WHEN** a user lacking `audit.read` calls an audit query endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding `audit.read` queries audit entries within their tenant
- **THEN** the system processes the request normally
