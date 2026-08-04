## Why

The `inventory` module exists today only as a data layer (ORM models + domain dataclasses) with no functional layer. Inventory is the next node on the critical operating path: it is fed by purchasing and consumed (via recipes) when orders are sold, and it is the only place that answers "how much do I have on hand and when do I reorder". Pilot restaurants need to track stock per branch and keep an honest movement audit trail instead of using spreadsheets. With `staff` now implemented, inventory's only hard dependency (`employees` for movement authorship) is satisfied; the `ingredients` table it references already exists (owned by the data-only `recipes` module), so inventory can be built independently.

## What Changes

- Add the **application + API layer** for the inventory module, mirroring the `menu`/`staff` reference modules (hexagonal: domain ports → application service → infrastructure repository → API router).
- Expose REST endpoints for **stock** (view on-hand per ingredient per branch, low-stock view, set reorder threshold) and **movements** (register stock in/out, physical recount adjustment, list movement history).
- Make stock changes **audited and atomic**: every change writes an `inventory_movements` row and updates the matching `inventory_stocks` row in one transaction. Stock for an ingredient/branch is auto-created on its first movement.
- Enforce business rules: `out` movements cannot drive on-hand negative; quantities must be positive; a recount sets an absolute counted value and records the computed delta as an `adjustment` movement.
- Enforce **multi-tenant + multi-branch isolation**: every read/write is scoped to the `tenant_id` from the subdomain middleware; both inventory tables are branch-scoped and the `branch_id` is validated against the tenant. Cross-module references (`ingredient_id`, `employee_id`) are validated against their tenant-scoped tables.
- Enforce **RBAC**: reads require `inventory.read`, writes require `inventory.adjust` (both already in the permissions catalog).
- Register the new router in `main.py`.
- No ORM model changes are expected — tables (`inventory_stocks`, `inventory_movements`) and the `inventory` registration in `models_registry.py` already exist.

## Capabilities

### New Capabilities
- `inventory-management`: Branch-scoped stock tracking with an auditable movement ledger — view/threshold stock, register in/out movements and physical recounts, all tenant-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/inventory/`: `domain/ports.py`, `application/use_cases/manage_inventory.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; restructure `domain/entities.py` to the project dataclass convention (business fields first, `id`/server-defaults optional).
- **Modified**: `src/restaurante/main.py` (include `inventory_router`).
- **Depends on** existing tables `ingredients` (recipes, data-only), `employees` (staff), `branches` (FK validation) and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **APIs**: new `/inventory/*` endpoints. No breaking changes to existing modules.
- **Tests**: new integration suite under `tests/modules/inventory/` (sqlite, FK enforcement) following the staff/menu pattern.
