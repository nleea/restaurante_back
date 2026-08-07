## ADDED Requirements

### Requirement: RBAC screen access

The frontend SHALL provide an RBAC management screen at `/rbac`, reachable only by users with
`rbac.manage`. Mutating controls SHALL additionally be gated by `auth.can('rbac.manage')`. This
gating is UX only; the backend enforces authorization independently.

#### Scenario: Authorized user reaches the screen
- **WHEN** a user with `rbac.manage` navigates to `/rbac`
- **THEN** the RBAC management screen is shown

#### Scenario: Unauthorized user is blocked
- **WHEN** a user without `rbac.manage` navigates to `/rbac`
- **THEN** they are redirected to the forbidden view (per the route guard)

### Requirement: Manage roles and their permissions

The screen SHALL let an authorized user list roles, create a role (name + optional
description), and view and edit a role's permission set against the global permissions catalog,
which SHALL be presented grouped by module.

#### Scenario: List and create roles
- **WHEN** the user opens the roles area
- **THEN** existing roles are listed
- **AND** the user can create a new role by providing a name

#### Scenario: View a role's permissions grouped by module
- **WHEN** the user opens a role
- **THEN** the global permission catalog is shown grouped by module with the role's current
  permissions marked

#### Scenario: Toggle a role permission
- **WHEN** the user enables or disables a permission for a role
- **THEN** the change is persisted via the RBAC API
- **AND** the displayed permission set reflects the server result

### Requirement: Manage user roles and overrides

The screen SHALL let an authorized user list the tenant's users, open a user to see their
roles, effective permissions, and explicit overrides, assign or revoke roles, and set or clear
per-user allow/deny overrides. The effective permissions SHALL be shown so the outcome of roles
plus overrides is visible.

#### Scenario: List users and open one
- **WHEN** the user opens the users area
- **THEN** the tenant's users are listed
- **AND** opening a user shows their roles, effective permissions, and overrides

#### Scenario: Assign and revoke a role
- **WHEN** the user assigns a role to (or revokes a role from) a user
- **THEN** the change is persisted via the RBAC API
- **AND** the user's effective permissions are refreshed

#### Scenario: Set and clear an override
- **WHEN** the user sets an allow or deny override on a permission, or clears it
- **THEN** the change is persisted via the RBAC API
- **AND** the effective permissions reflect that roles ∪ allow − deny
