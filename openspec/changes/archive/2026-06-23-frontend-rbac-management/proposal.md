## Why

The frontend foundation (HTTP + auth + permission-gated routing) is in place but its first
real consumer — the **RBAC/users management screen** — does not exist; `/rbac` is a guarded
placeholder. The backend exposes a full `/rbac` management API (roles, role↔permission,
user↔role, per-user overrides), all gated by `rbac.manage`, **except it cannot list the
tenant's users**: every per-user operation requires a `user_id` known in advance, and no
endpoint returns them. That gap blocks the "users" half of the screen. This change closes it
with a minimal read endpoint and builds the full screen on the foundation, with the
established "El Pase" visual identity.

## What Changes

**Backend (small, additive):**
- Add `GET /rbac/users` — list the current tenant's users (`id`, `email`, `name`,
  `username`, `is_active`, `last_login_at`), gated by `rbac.manage`, tenant-scoped. Backed by
  a new `list_tenant_users(tenant_id)` on the RBAC repository + service and a
  `UserSummaryResponse` schema. Read-only; no user creation here.

**Frontend (the screen, on the foundation):**
- Replace the `/rbac` placeholder with a management screen gated by `rbac.manage`, in two areas:
  - **Roles** — list roles, create a role, and edit a role's permission set against the
    global permissions catalog (`GET /rbac/permissions`), grouped by module.
  - **Users** — list users, open a user to see effective permissions and roles, assign/revoke
    roles, and set/clear per-user allow/deny overrides.
- A typed API service layer (`services/rbac.api.ts`) over the foundation's Axios instance, a
  store/composable for RBAC state, and PrimeVue components (DataTable, Dialog, …) themed with
  the `ember` accent. Views designed with the frontend-design skill ("El Pase").
- Gate destructive/mutating controls in the UI by `rbac.manage` (UX; backend still enforces).

## Impact

- **Affected backend:** `modules/identity` — rbac router, `RbacService`, RBAC repository,
  schemas, and tests.
- **Affected frontend:** new `views/rbac/*`, `components/rbac/*`, `services/rbac.api.ts`,
  RBAC state, router wiring, and tests. Builds on `frontend-foundation` (`http`, `auth.can`,
  guards) and the "El Pase" tokens.
- **Capabilities:** adds `rbac-management` (backend list-users requirement) and
  `frontend-rbac` (UI requirements).
- **Deferred (non-goals):** creating/inviting users, deleting roles, editing user profile
  fields, and branch-scoped role assignment UI.
