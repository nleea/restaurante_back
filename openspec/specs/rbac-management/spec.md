# rbac-management

## Purpose

Server-side support for managing access control, beyond the resolution/enforcement that
already lives in the identity module. This capability covers RBAC-administration surfaces the
core `/rbac` API did not expose: listing the tenant's users so an administrator can manage their
roles and overrides, and provisioning a tenant user (with an inline person and optional initial
role). All endpoints are gated by `rbac.manage` and tenant-scoped by the subdomain. Future
RBAC-management additions accrete here.

## Requirements

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

### Requirement: Provision a tenant user

The system SHALL expose `POST /rbac/users`, gated by `rbac.manage`, that creates a new tenant user together with an inline person, in a single transaction. The request SHALL carry the person's `first_name` and `last_name` (and MAY carry `document_number` and `phone`), the login `email` and `password`, and MAY carry a `role_id` to assign to the new user. The system SHALL store the password hashed (never in plaintext), link the created `users.person_id` to the created person, and SHALL reject a duplicate email within the tenant. When a `role_id` is supplied, the system SHALL assign that role to the new user with the same cache invalidation as the existing role-assignment path. The response SHALL include the new user's `id`, `email`, `name`, `is_active`, and the created `person_id`.

#### Scenario: Creates a user with an inline person

- **WHEN** an authorized user `POST`s `/rbac/users` with `first_name`, `last_name`, `email`, and `password`
- **THEN** the system responds `201` with the new user's `id`, `email`, `name`, `is_active`, and `person_id`, and the password is stored only as a hash

#### Scenario: Optional initial role is assigned

- **WHEN** the request includes a valid `role_id`
- **THEN** the new user is assigned that role and its effective permissions reflect the role immediately (cache invalidated)

#### Scenario: Duplicate email within the tenant is rejected

- **WHEN** the `email` already belongs to a user of the same tenant
- **THEN** the system responds `409` and creates neither a user nor a person

#### Scenario: Requires the manage permission

- **WHEN** a caller without `rbac.manage` attempts `POST /rbac/users`
- **THEN** the system responds `403` and creates nothing
