## 1. Backend — user provisioning (`POST /rbac/users`)

- [x] 1.1 Add request/response schemas: `CreateUserRequest` (`first_name`, `last_name`, `email`, `password`, optional `document_number`, `phone`, `role_id`) and a provisioning response (user `id`, `email`, `name`, `is_active`, `person_id`).
- [x] 1.2 Add a `create` path that inserts a `PersonModel` (first/last + optional doc/phone) and a `UserModel` (tenant-scoped, `person_id` linked, `name = "<first> <last>"`, `hashed_password` via the shared `Argon2PasswordHasher`, `is_active = true`) in one transaction.
- [x] 1.3 Wire a provisioning use case (user repo create + hasher + RBAC `assign_user_role` for the optional `role_id`, reusing cache invalidation); reject duplicate tenant email with `409`.
- [x] 1.4 Add `POST /rbac/users` to the rbac router gated by `rbac.manage`, returning `201` with the provisioning response.
- [x] 1.5 Integration tests: creates person+user; password stored hashed; optional role assigned (effective permissions reflect it); `409` on duplicate email; `403` without `rbac.manage`.
- [x] 1.6 Run `ruff`, `mypy`, and `pytest` green.

## 2. Frontend — staff service & store

- [x] 2.1 Add `services/staff.api.ts`: `listEmployees({branchId?, active?})`, `getEmployee`, `createEmployee`, `updateEmployeeRole`, `deactivateEmployee`, `listShifts`, `createShift`, `updateShift`, `deleteShift`, plus `provisionUser` (`POST /rbac/users`).
- [x] 2.2 Add `stores/staff.ts`: employees state, planned-shifts-by-employee, and label maps built from `rbac.api.listUsers` + `rbac.api.listRoles` + the branch store.
- [x] 2.3 Implement the add-employee flow in the store: `provisionUser(...)` → `createEmployee(...)` for the active branch + chosen role; surface the `409`/conflict errors.
- [x] 2.4 Implement role change, deactivate, and shift create/edit/delete actions, refreshing affected state.
- [x] 2.5 Unit tests: label resolution (no UUIDs leak), add-employee orchestration (two calls, conflict path), role change, shift `end > start` guard.

## 3. Frontend — staff screen (employees + shifts)

- [x] 3.1 Add the `/staff` route (`meta.requiresAuth`, `meta.permission = 'staff.read'`) and a "Personal" sidebar link gated by `staff.read`.
- [x] 3.2 Build `views/StaffView.vue` wrapping `AppShell`, using the mobile-first master–detail pattern (single `selected` ref + `max-lg:hidden`).
- [x] 3.3 Build `components/staff/EmployeesPanel.vue`: list with resolved labels (name/email, role, branch, active), active-state filter, default scope to the active branch, and an "Add employee" action (form: name, email, password, role) gated by `staff.manage`.
- [x] 3.4 Build `components/staff/EmployeeDetail.vue`: role selector + deactivate (gated by `staff.manage`), and a planned-shifts sub-panel (list + create/edit/delete with the `end > start` rule).
- [x] 3.5 Style with the "El Pase" design system; keep responsive `hidden` classes on wrapping `<span>`s (PrimeIcons `.pi` caveat).

## 4. Validation

- [x] 4.1 Frontend: type-check, lint (oxlint + eslint), unit tests, and production build all green.
- [x] 4.2 Verified at the test level: backend integration tests cover provisioning (create, hashed login, role assignment, 409, 403) and frontend unit tests cover the two-step add flow, label resolution (no UUIDs), role change, and the shift `end > start` guard; type-check/lint/build green. Live browser walkthrough not run in this pass.
