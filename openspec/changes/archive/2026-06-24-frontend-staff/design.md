## Context

The backend `staff` module is complete (employees, planned shifts, attendance, commissions) but un-usable from a client: `POST /staff/employees` requires `person_id` + `user_id`, and the codebase exposes **no endpoint to create a person or a tenant user** (tests insert `PersonModel`/`UserModel` directly). `EmployeeResponse` returns only UUIDs (`branch_id`, `person_id`, `user_id`, `role_id`). Meanwhile the resolvable directories all exist: `GET /rbac/users` (id, email, name, …), `GET /rbac/roles`, and the just-shipped `GET /branches` + branch context store.

Relevant models: `UserModel` is tenant-scoped, has a nullable `person_id` FK to `persons`, `email` (unique per tenant via `uq_users_tenant_email`), `hashed_password`, `name`, `is_active`. `PersonModel` is global (not tenant-scoped) with required `first_name`/`last_name` plus optional `document_*`, `phone`, etc. The user repository has no create method today; RBAC has `assign_user_role` with cache invalidation. The shared `Argon2PasswordHasher` lives in `shared/security/password`.

## Goals / Non-Goals

**Goals:**
- Make it possible to create an employee end-to-end from the frontend.
- Add the smallest backend piece that unblocks it: provision a tenant user (+ inline person, + optional role) via identity.
- Ship a complete, useful staff slice: employees (list/add/edit-role/deactivate) and planned shifts, with human labels instead of UUIDs.

**Non-Goals:**
- Attendances (check-in/out) and commissions UI — deferred to a follow-up change.
- A general persons CRUD / persons listing endpoint (not needed: employees are labeled by their linked user).
- Self-service password reset, user editing, or deactivating users (only employee deactivate).
- Enriching `EmployeeResponse` with names server-side — labels are resolved client-side.

## Decisions

### 1. Provision users in identity, keep `POST /staff/employees` unchanged
The missing capability is "create a tenant user + person". That is an identity concern, so it goes in identity as `POST /rbac/users` (next to the existing `GET /rbac/users`), gated by `rbac.manage`. The staff endpoint already accepts `person_id`/`user_id`, so it needs no change. **Alternative considered:** extend `POST /staff/employees` to create person+user inline atomically (one call, no orphan). Rejected for now because it pushes user-creation + password hashing + RBAC assignment into the staff module, blurring the boundary; the two-call flow keeps each module single-responsibility. The trade-off (a user created without an employee if the second call fails) is minor and visible — the orphan user shows up in `GET /rbac/users` and the employee can be retried.

### 2. Inline person on user creation (mirror `customers`)
`customers.create_customer` already establishes the "create the person inline" pattern. `POST /rbac/users` takes `first_name`, `last_name`, optional `document_number`/`phone`, plus `email`, `password`, optional `role_id`. It creates the person, then the user with `person_id` linked and `name = "<first> <last>"`, hashing the password with the shared `Argon2PasswordHasher`. **Alternative considered:** require a pre-existing `person_id`. Rejected — there is no way to create a person, so inline is mandatory.

### 3. Optional role assignment reuses the RBAC path
When `role_id` is provided, assignment goes through the existing RBAC service `assign_user_role` so the permission cache is invalidated correctly (a raw insert into `user_roles` would leave a stale cache). The same `role_id` the frontend uses here is also passed to `POST /staff/employees` as the employee's job role, so "role" stays a single choice in the UI. **Alternative:** make role mandatory. Kept optional at the API to stay flexible; the frontend's add-employee form will always send one.

### 4. Frontend resolves labels client-side
Employee responses are UUIDs; the screen joins them against three already-available directories: users (`rbac.api.listUsers`), roles (`rbac.api.listRoles`), and branches (branch store). This mirrors how the RBAC screen already resolves ids and avoids any `EmployeeResponse` change. Maps are built once per load (`Map<id, label>`).

### 5. Master–detail, branch-scoped, following the RBAC reference
`StaffView` uses the project's mobile-first master–detail pattern (one `selected` ref, `max-lg:hidden`, no router sub-routes). `EmployeesPanel` is the master list (filter by active; default scope to the active branch); `EmployeeDetail` shows role/status controls and a planned-shifts sub-panel. New employees are created for the **active branch** (from the branch context shipped in `frontend-branch-context`). Single source of truth for "which branch" is the branch store.

### 6. Scope to employees + shifts (small complete system)
Per the project's design gate ("prefer a small complete system over a large half-built one"), this change ships employees + planned shifts only; attendances and commissions are a clearly-marked follow-up. Shifts are low-risk (date + two times + an `end > start` rule already enforced server-side and mirrored client-side).

## Risks / Trade-offs

- **Orphan user if employee creation fails** (two-call flow) → the user is visible in `GET /rbac/users` and the employee can be retried; the add-employee flow surfaces the failure and does not silently swallow it. A future atomic onboarding endpoint can supersede this.
- **Password handling on the client** → the add-employee form sends an initial password over HTTPS to `POST /rbac/users`; it is hashed server-side and never echoed back. No plaintext is stored client-side.
- **Label maps go stale if users/roles change mid-session** → the store reloads users/roles alongside employees; actions that change a role refresh the affected employee.
- **Person uniqueness** → `create_employee` already rejects a person/user already linked to an employee (`409`); the add flow maps that to a form error.
- **Empty pilot data** → the seed creates no employees; with this change a pilot can add their first employee immediately, so the screen is usable from day one.

## Migration Plan

1. Backend: add `POST /rbac/users` (schemas, provisioning use case wiring user repo create + hasher + RBAC assignment), register nothing new (router already mounted). Integration tests: create user+person, `409` duplicate email, optional role assignment, `rbac.manage` gate. Run `ruff`/`mypy`/`pytest`.
2. Frontend: `services/staff.api.ts` (+ reuse `rbac.api`), `stores/staff.ts`, `views/StaffView.vue`, `components/staff/EmployeesPanel.vue` + `EmployeeDetail.vue` (+ shifts), `/staff` route + "Personal" nav link. Unit tests for store/service.
3. Validate: type-check, lint, unit, build (frontend); full backend gate.

Rollback: the backend endpoint is additive; the frontend route/link can be removed without affecting other screens.

## Open Questions

- Should `POST /rbac/users` allow `username` in addition to `email`? Default: email only for now (username stays nullable).
- Should deactivating an employee also deactivate the underlying user account? Default: no — employee and user lifecycles are separate; only the employee is deactivated here.
