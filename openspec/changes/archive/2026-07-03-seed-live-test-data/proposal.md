## Why

The current `scripts/seed.py` only creates the bare minimum to log in (demo tenant, one branch, an admin user, and the RBAC baseline). It produces an empty system: no supplies, no recipes, no products, no orders, no delivery routes. That makes it impossible to run a credible **live demo / pilot rehearsal** of the daily restaurant flow, and it forces every developer to hand-create data to test a feature. We need a richer, idempotent seed that fills the operational tables end-to-end so the 3 pilot restaurants (the project's bar for "indispensable") can walk through a realistic day without falling back to Excel or paper.

## What Changes

- Add a **demo dataset seed** that populates the full operational chain on top of the existing demo tenant/branch/admin, covering the cross-module flow: **supplies (insumos) → purchasing → inventory stock → recipes (BOM) → menu/products → orders → kitchen → delivery routes (rutas) → cash → finance**.
- Seed **inventory supplies (insumos)** with realistic units of measure, categories, and current stock levels per branch.
- Seed **delivery routes (rutas)** with drivers (employees), assignable orders, and the explicit delivery states (pending → assigned → in transit → delivered/failed).
- Seed supporting master data: staff/drivers, customers, catalog/menu products and variants, recipes linking products to supplies, and a handful of sample orders threaded through kitchen, cash, and delivery so reports are non-empty.
- Make the seed **idempotent and layered** (re-runnable without duplicating rows) and **opt-in** via a flag/entrypoint so the existing minimal seed remains the default for unit tests.
- Provide a single documented command to load and (optionally) reset the demo dataset.

## Capabilities

### New Capabilities
- `demo-seed-data`: A re-runnable demo/test data loader that fills the operational tables (supplies, purchasing, inventory, recipes, menu, orders, kitchen, delivery routes, cash, finance) with realistic, tenant- and branch-scoped data for live testing, plus a documented run/reset workflow.

### Modified Capabilities
<!-- None: this change adds tooling/data, it does not alter any module's spec-level behavior or requirements. -->

## Impact

- **New/affected code**: `backend/scripts/seed.py` (extended or split into a `scripts/seed/` package), reusing existing domain models and repositories across the `inventory`, `purchasing`, `delivery`, `catalog`, `menu`, `recipes`, `orders`, `kitchen`, `customers`, `staff`, `cash`, and `finance` modules.
- **Data**: writes rows only under the `demo` tenant and its branch(es); must respect `BranchScopedMixin` / `TenantScopedMixin` (`tenant_id` + `branch_id`) and the automatic tenant filter.
- **Dependencies**: no new runtime dependencies; runs against the same async SQLAlchemy `SessionFactory` and requires migrations applied (`alembic upgrade head`).
- **Docs**: update `backend/CLAUDE.md` command list and add usage notes for loading/resetting the demo dataset.
- **Out of scope**: no production data, no schema/migration changes, no changes to module business logic.
