## Why

The `staff` module today exists only as a data layer (ORM models + domain dataclasses) with no functional layer: no repository ports, no application service, no API. Staff (employees) is a foundational dependency for the critical operating path — delivery drivers, commissions tied to orders, and shift/attendance tracking all hang off employees. Without a working staff module the pilot restaurants cannot register their workforce, schedule shifts, or attribute commissions, and downstream modules (delivery, orders) have nothing to reference. It is the lowest node in the dependency graph, so it should be implemented first.

## What Changes

- Add the **application + API layer** for the staff module, mirroring the `menu`/`identity` reference modules (hexagonal: domain ports → application service → infrastructure repository → API router).
- Expose REST endpoints for managing **employees** (link a `person` + login `user` + `role` to a branch), **planned shifts**, **attendances** (clock-in/out), and **commissions**.
- Enforce **multi-tenant isolation**: every read/write is scoped to the `tenant_id` resolved by the subdomain middleware; tenant-level entities use `TenantScopedMixin`, branch-level entities (`employees`, `planned_shifts`) carry an explicit `branch_id` validated against the tenant.
- Enforce **RBAC**: reads require `staff.read`, writes require `staff.manage` (both already declared in the permissions catalog).
- Register the new router in `main.py`.
- No ORM model changes are required — the existing tables (`employees`, `planned_shifts`, `attendances`, `commissions`) and the `staff` registration in `models_registry.py` already exist. No new migration unless a constraint gap is found.

## Capabilities

### New Capabilities
- `staff-management`: Branch-scoped workforce management — CRUD for employees, planned shifts, attendance (clock-in/out) and commissions, fully tenant-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/staff/`: `domain/ports.py`, `application/use_cases/manage_staff.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; extend `domain/entities.py` if needed.
- **Modified**: `src/restaurante/main.py` (include `staff_router`).
- **Depends on** existing tables `persons`, `users`, `roles`, `branches` (FK validation) and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter in `shared/tenancy/filtering.py`, `shared/domain/errors` (`NotFoundError`, `ConflictError`).
- **APIs**: new `/staff/*` endpoints. No breaking changes to existing modules.
- **Tests**: new integration test suite under `tests/` following the menu test pattern (sqlite).
