## ADDED Requirements

### Requirement: List the current tenant's branches

The system SHALL expose a read-only `GET /branches` endpoint that returns the branches belonging to the tenant resolved from the request (via the existing subdomain tenancy middleware). The endpoint SHALL require an authenticated session but SHALL NOT require any RBAC permission code, since selecting one's working branch is a session primitive. Each returned branch SHALL include `id`, `code`, `name`, and `is_primary`. The endpoint SHALL return only active branches (`is_active = true`) and SHALL never return branches of another tenant.

#### Scenario: Authenticated user lists their tenant's branches

- **WHEN** an authenticated user sends `GET /branches`
- **THEN** the system responds `200` with a JSON array of that tenant's active branches, each containing `id`, `code`, `name`, and `is_primary`

#### Scenario: Tenant isolation

- **WHEN** a user authenticated for tenant A requests `GET /branches`
- **THEN** the response contains only branches whose `tenant_id` is tenant A, and no branch belonging to any other tenant

#### Scenario: Inactive branches are excluded

- **WHEN** the tenant has a branch with `is_active = false`
- **THEN** that branch is omitted from the `GET /branches` response

#### Scenario: Unauthenticated request is rejected

- **WHEN** a request to `GET /branches` carries no valid access token
- **THEN** the system responds `401` and returns no branch data
