## ADDED Requirements

### Requirement: List tenant users

The system SHALL expose a read-only endpoint that lists the current tenant's users, for use by
RBAC management. The endpoint SHALL require the `rbac.manage` permission and SHALL be scoped to
the tenant resolved by the subdomain. Each entry SHALL include `id`, `email`, `name`,
`username`, `is_active`, and `last_login_at`. The endpoint SHALL NOT create, modify, or delete
users.

#### Scenario: Authorized admin lists users
- **WHEN** a user with `rbac.manage` requests the tenant's users
- **THEN** the system returns the tenant's users with `id`, `email`, `name`, `username`,
  `is_active`, and `last_login_at`

#### Scenario: Tenant isolation
- **WHEN** an authorized user for tenant A lists users
- **THEN** only users belonging to tenant A are returned

#### Scenario: Missing permission is rejected
- **WHEN** a user without `rbac.manage` requests the user list
- **THEN** the system rejects the request (403)
