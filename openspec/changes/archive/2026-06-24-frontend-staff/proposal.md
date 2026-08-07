## Why

The backend `staff` module (employees, planned shifts, attendance, commissions) has a complete API, but **no employee can be created from a client today**: `POST /staff/employees` requires a `person_id` and a `user_id`, and neither persons nor tenant users have any creation endpoint (the backend tests insert them straight into the DB). So a staff screen would be permanently empty and unusable for the pilot restaurants, who need to add their own people. This change closes that provisioning gap and then builds the staff management screen on top of it.

## What Changes

- **Backend — user provisioning** (identity): add `POST /rbac/users` (gated by `rbac.manage`) that creates a `Person` (inline: first/last name, optional document/phone) **and** a tenant `User` (email + password, linked via `users.person_id`) atomically, and optionally assigns an RBAC role to the new user. Returns the user summary plus its `person_id`. This is the missing piece that lets a client provision the `person_id`/`user_id` that `POST /staff/employees` already expects. `POST /staff/employees` is **unchanged**.
- **Frontend — staff screen** (first complete slice: **employees + planned shifts**):
  - A `/staff` route (gated by `staff.read`; mutations by `staff.manage`) with a "Personal" nav entry, following the mobile-first master–detail pattern (the RBAC screen is the reference).
  - **Employees list/detail**: resolve the raw-UUID employee responses into human labels client-side — `user_id` → name/email via `GET /rbac/users`, `role_id` → name via `GET /rbac/roles`, `branch_id` → name via the branch context (`GET /branches`). Filter by active/branch.
  - **Add employee**: one form that provisions the user (new `POST /rbac/users`) then creates the employee (`POST /staff/employees`) for the active branch + chosen role.
  - **Edit role / deactivate** an employee.
  - **Planned shifts** per employee: list, create (date + start/end time with the `end > start` rule), edit, delete.
- **Deferred to a follow-up change** (explicitly out of scope here): attendances (check-in/out) and commissions. They are operational, not core to standing up the workforce, and keeping them out keeps this a small complete system.

## Capabilities

### New Capabilities
- `frontend-staff`: the Staff management screen — employees (list/add/edit-role/deactivate) and their planned shifts, scoped to the active branch, with permission gating and client-side label resolution.

### Modified Capabilities
- `rbac-management`: gains a **user-provisioning** requirement — creating a tenant user with an inline person (and optional initial role) via `POST /rbac/users`. (Existing rbac requirements are unchanged; this adds a new one.)

## Impact

- **Backend**: new `POST /rbac/users` route + request/response schemas; a provisioning use case wiring the user repo (new `create` path), the shared `Argon2PasswordHasher`, and the existing RBAC role-assignment (for cache-correct permissions). New integration tests (creates person+user, email uniqueness `409`, optional role assignment, `rbac.manage` gate). No DB migration (`persons`/`users` tables exist).
- **Frontend**: new `services/staff.api.ts`; new `stores/staff.ts`; new `views/StaffView.vue` + `components/staff/EmployeesPanel.vue` + `EmployeeDetail.vue` (with a shifts sub-panel); a `/staff` route and a "Personal" sidebar link; reuse of `rbac.api` (users, roles) and the branch store for labels. Unit tests for the store and service.
- **Unblocks**: a real workforce screen for the pilots; establishes the user-provisioning endpoint that other modules (e.g. assigning logins) can reuse.
