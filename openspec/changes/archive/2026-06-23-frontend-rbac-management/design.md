## Context

First consumer of `frontend-foundation`. The backend RBAC model (confirmed in
`modules/identity`):

- **Permissions** are a global catalog: `GET /rbac/permissions` → `{id, code, name, module,
  description}`. Codes are `"<module>.<action>"`.
- **Roles** are tenant-scoped: `GET/POST /rbac/roles` (`{id, name, description, is_global,
  is_active, tenant_id}`). `is_global` roles (e.g. `admin`) are shared/seeded.
- **Role permissions:** `GET /rbac/roles/{id}/permissions` → `{role_id, permissions: code[]}`;
  `PUT` sets the whole set; `POST/DELETE /rbac/roles/{id}/permissions/{code}` toggle one.
- **User access:** `GET /rbac/users/{id}/access` → `{user_id, roles[], effective_permissions:
  code[], overrides: [{permission_id, effect}]}`. `effective = (roles ∪ allow) − deny`,
  cached server-side.
- **User mutations** (all `204`): `POST/DELETE /rbac/users/{id}/roles/{role_id}`;
  `PUT/DELETE /rbac/users/{id}/permissions/{code}` with `{effect: "allow"|"deny"}`.
- **Everything is gated by `rbac.manage`** at the router level; the backend enforces
  independently of any UI gate.

The gap: **no endpoint lists tenant users**, so per-user management has no entry point.
`UserModel` is tenant-scoped with `id, email, name, username, is_active, last_login_at`.

Constraints inherited: English identifiers; tenant by subdomain (no `tenant_id` in bodies);
frontend gating is UX only; "El Pase" design tokens in `src/assets/main.css`.

## Goals / Non-Goals

**Goals:**
- A read-only `GET /rbac/users` (tenant-scoped, `rbac.manage`) returning user summaries.
- A `/rbac` screen: manage roles + role permission sets, and manage users' roles + overrides.
- Typed frontend API layer over the foundation Axios instance; RBAC state; PrimeVue UI themed
  to "El Pase"; destructive controls gated by `auth.can('rbac.manage')`.
- Tests on both sides.

**Non-Goals:** user creation/invite, role deletion, editing user profile fields, branch-scoped
assignment UI, and any change to how effective permissions are computed/cached.

## Decisions

**1. Backend: `GET /rbac/users` lives in the existing rbac router.**
Add `list_tenant_users(tenant_id) -> list[User]` to `RbacRepository` (SQLAlchemy: select
`UserModel` filtered by tenant, ordered by `name`) and a passthrough on `RbacService`; expose
a `UserSummaryResponse` (`id, email, name, username, is_active, last_login_at`). It inherits
the router's `rbac.manage` dependency and tenant scoping. Rationale: the screen's user list is
a function *of RBAC management*, the router already carries the right guard, and reusing it
avoids a second auth surface. Read-only — user lifecycle is out of scope.

**2. Frontend structure mirrors the foundation's conventions.**
`services/rbac.api.ts` exports typed functions (`listRoles`, `createRole`,
`getRolePermissions`, `setRolePermissions`, `listPermissions`, `listUsers`, `getUserAccess`,
`assignRole`, `revokeRole`, `setOverride`, `removeOverride`) over the shared `http` instance.
A `stores/rbac.ts` Pinia store (or a `useRbac` composable) holds roles/permissions/users and
the currently-open detail. Views under `views/rbac/`, reusable pieces under `components/rbac/`.
Rationale: consistency with `lib/`, `stores/`, `views/` already established.

**3. Two-tab screen: Roles and Users — not one giant grid.**
`/rbac` hosts a tabbed layout. **Roles tab:** a list/table of roles; selecting one opens a
permission-set editor showing the global catalog grouped by `module`, with checkboxes bound to
the role's codes (persist via `PUT` for a bulk save, or per-toggle `POST/DELETE` for instant
edits — see Decision 4). **Users tab:** a table of users (from the new endpoint); selecting one
opens an access panel: their roles (assign/revoke), effective permissions (read-only, derived),
and explicit overrides (allow/deny/clear). Rationale: roles and users are distinct mental
models; tabs keep each task focused and match how admins think ("set up roles" vs "give this
person access").

**4. Role permission editing uses optimistic per-toggle writes with a bulk fallback.**
Default to per-permission `POST/DELETE /rbac/roles/{id}/permissions/{code}` on each checkbox
toggle (instant, low-risk, matches the 204 endpoints), reconciling against the server response;
offer a "Save all" path via `PUT` when editing many at once. Rationale: per-toggle is the
simplest correct model and gives immediate feedback; `PUT` exists for batch. Trade-off: more
requests under heavy editing — acceptable for an admin screen.

**5. The UI gate is `auth.can('rbac.manage')`, consistent with the route guard.**
The route already requires `rbac.manage`; within the screen, mutating controls
(create role, toggle permission, assign role, set override) are additionally hidden/disabled
when `!auth.can('rbac.manage')`. This is belt-and-suspenders UX — the backend is the real
gate. A small reusable `v-can`-style helper or a computed may back this. Rationale: a user who
reaches the screen always has `rbac.manage` today, but encoding the gate keeps the pattern
honest for finer-grained permissions later (e.g. a future `rbac.read`).

**6. Visual identity: extend "El Pase", do not reinvent.**
Reuse the existing tokens (graphite/steel/ember/paper, Bricolage/Plex). The authenticated app
is the light "working surface". PrimeVue's primary is already remapped to `ember`, so DataTable
selection, buttons, and toggles inherit the accent. The screen's signature should be a
*station-label* treatment of roles/permission groups (mono module headers, the same docket
vocabulary), not a new aesthetic. The frontend-design skill guides the specific layout, but the
palette/type are fixed by the foundation. Rationale: a management screen must feel like the
same product as the login; identity consistency over novelty here.

**7. Permission catalog is grouped and labeled by module in the UI.**
The flat `code[]` is grouped by the `module` field (`menu`, `inventory`, `rbac`, …) into
labeled sections, each action shown by its `name`/`description`. Rationale: 30+ codes are
unusable as a flat list; module grouping mirrors the backend's own taxonomy and makes intent
scannable.

## Risks / Trade-offs

- **Per-toggle writes amplify requests** (Decision 4) → acceptable on a low-traffic admin
  screen; the `PUT` bulk path is the escape hatch.
- **No user list pagination yet** → tenants are small (pilot = a handful of staff); `GET
  /rbac/users` returns all. If a tenant grows large, add `limit/offset` later — noted, not built.
- **Overrides are powerful and confusing** (allow/deny on top of roles) → mitigate with a clear
  three-state control (inherited / allow / deny) and by always showing the *effective* result
  next to the override, so the admin sees the outcome.
- **`is_global` roles** (e.g. `admin`) shared across tenants → the UI must not imply a tenant
  can delete/rename a global role; show them read-only or clearly flagged. (Role deletion is
  out of scope anyway.)
- **Frontend gate ≠ security** → reiterated; never treat hidden as forbidden.

## Migration Plan

1. Backend: add `list_tenant_users` (repo + service), `UserSummaryResponse`, and the
   `GET /rbac/users` route; tests. No schema/migration change — reads existing `users`.
2. Frontend: API layer → store → components → the two-tab screen → route swap (placeholder →
   real screen) → design pass with frontend-design.
3. Prove against the seeded tenant: `admin@demo.com` sees roles, the permission catalog, the
   user list (incl. itself), can create a role, toggle a permission, assign/revoke a role, and
   set/clear an override, with effective permissions updating.

## Open Questions

- **Bulk vs per-toggle as the default** for role permissions (Decision 4) — ship per-toggle;
  revisit if admins ask for an explicit save/discard model.
- **Show `is_global` roles editable or read-only?** (Default: visible, permission set
  read-only for global roles to avoid cross-tenant surprises; confirm during build.)
- **Surface `last_login_at` in the user table?** (Default: yes, as a quiet mono timestamp — it
  helps admins spot dormant accounts; cheap to include.)
