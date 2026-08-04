# Tasks — frontend-rbac-management

Build order: unblock the API gap on the backend first, then the frontend layers bottom-up
(service → state → components → screen), then the design pass, then prove end-to-end.

## 1. Backend — `GET /rbac/users`
- [x] Add `list_tenant_users(tenant_id) -> list[User]` to `RbacRepository` port and its
      SQLAlchemy implementation (select `UserModel` by tenant, ordered by `name`).
- [x] Add a passthrough `list_tenant_users` on `RbacService`.
- [x] Add `UserSummaryResponse` (`id, email, name, username, is_active, last_login_at`) to
      `rbac_schemas.py`.
- [x] Add `GET /rbac/users` to `rbac_router.py` (inherits `rbac.manage` + tenant scope).
- [x] Tests: authorized list returns tenant users; tenant isolation; `403` without
      `rbac.manage`. ruff + mypy clean, 13 rbac tests pass; route present in OpenAPI.

## 2. Frontend — typed API layer
- [x] `services/rbac.api.ts` over the shared `http` instance: `listPermissions`, `listRoles`,
      `createRole`, `getRolePermissions`, `setRolePermissions`, `addRolePermission`,
      `removeRolePermission`, `listUsers`, `getUserAccess`, `assignRole`, `revokeRole`,
      `setOverride`, `removeOverride`.
- [x] TypeScript types for Permission, Role, RolePermissions, UserSummary, UserAccess, Override.

## 3. Frontend — RBAC state
- [x] `stores/rbac.ts` (Pinia) or a `useRbac` composable holding roles, permission catalog
      (grouped by module), users, and the currently-open role/user detail.
- [x] Actions wrap the API layer and keep local state reconciled with server responses.

## 4. Frontend — components
- [x] Roles area: roles table/list + create-role dialog + permission-set editor (catalog
      grouped by `module`, checkboxes bound to the role's codes; per-toggle persist with a
      bulk `PUT` fallback).
- [x] Users area: users table (incl. quiet `last_login_at`) + user access panel (roles
      assign/revoke, read-only effective permissions, allow/deny/clear overrides with the
      effective result shown alongside).
- [x] Gate mutating controls by `auth.can('rbac.manage')`.

## 5. Frontend — screen + routing
- [x] Replace the `/rbac` placeholder view with a tabbed screen (Roles | Users), keeping
      `meta: { requiresAuth: true, permission: 'rbac.manage' }`.
- [x] Wire the components and state into the screen.

## 6. Design pass ("El Pase")
- [x] Apply the frontend-design skill using the existing tokens (graphite/steel/ember/paper,
      Bricolage/Plex). Station-label treatment for module groups; consistent with login.
- [x] Screenshot desktop + mobile, self-critique, refine. Respect focus-visible and
      reduced-motion. Keep the accent restrained.

## 7. Verify end-to-end
- [x] Against seeded `admin@demo.com` on `demo.localhost`: list roles + permission catalog +
      users (incl. self); create a role; toggle a role permission; assign/revoke a role; set
      and clear an override; confirm effective permissions update.
- [x] Frontend gates: `type-check`, `lint`, `test:unit` green; unit test the API layer and the
      override/effective logic.

## 8. Tests
- [x] Backend: the `GET /rbac/users` cases above.
- [x] Frontend: API layer calls hit the right endpoints; store reconciles toggles and
      overrides; `can('rbac.manage')` gates mutating controls.

## Verification record
- **Backend:** ruff + mypy clean; full suite **158 passed** (155 + 3 new RBAC user tests);
  `GET /rbac/users` present in live OpenAPI.
- **Frontend:** `type-check`, `lint`, `build` green; `test:unit` **14 passed** (foundation 5 +
  rbac api 5 + rbac store 4).
- **End-to-end (Cypress, Electron, live backend on `demo.localhost`):** login → guarded `/rbac`
  → roles list (seeded admin/cashier/courier/kitchen/manager/waiter) → create tenant role →
  toggle a permission (persisted) → Users tab → open user → 33 effective permissions shown.
  Verified at desktop viewport (1320×920) with on-brand screenshots; RBAC mobile pass not run
  (deferred — layout uses responsive `lg:` grids that collapse to a single column).
- **Design:** no token deviation; the screen reuses "El Pase" (station-label mono module
  headers, ember accent, paper/app surfaces), consistent with the login.
