## Context

The backend is a FastAPI + async SQLAlchemy 2.0 hexagonal modular monolith with row-level multi-tenancy (`tenant_id` + `branch_id` via `BranchScopedMixin`/`TenantScopedMixin` in `shared/database.py:53-82`). The existing `scripts/seed.py` is intentionally minimal — demo tenant (`demo`), branch (`MAIN`), admin user (`admin@demo.com`/`admin1234`), and the RBAC catalog — and is the baseline that tests and local login rely on.

To run a credible live demo/pilot rehearsal we need the operational tables populated end-to-end: supplies (insumos) → inventory stock → suppliers/purchasing → menu products/variants → recipes (BOM) → customers → delivery routes (rutas)/drivers/runs → orders → payments → cash → finance. The seed runs **outside an HTTP request**, so the automatic tenant ContextVar filter is inactive and every row's `tenant_id`/`branch_id` must be set explicitly. Most FKs use `ondelete="RESTRICT"`, so parents must be created before children. Statuses are plain `String` columns (no DB enums); money is `Numeric(12,2)` Decimal, quantities `Numeric(12,3)`, geo `Numeric(10,7)`.

## Goals / Non-Goals

**Goals:**
- An idempotent, re-runnable demo loader that fills the full operational chain under the `demo` tenant/branch.
- Reuse the existing minimal seed (tenant/branch/admin/RBAC) instead of duplicating it.
- Realistic Colombian restaurant data (units kg/g/L/ml/unit, neighborhoods, Nequi/Daviplata-style cash, drivers as employees).
- A single documented command to load, and a documented way to reset.
- Keep `scripts.seed` (the test/login baseline) unchanged and decoupled from the demo dataset.

**Non-Goals:**
- No schema or migration changes; no new runtime dependencies.
- No changes to any module's business logic or API.
- No production data; writes only under the `demo` tenant.
- No factory framework adoption (the project uses plain model constructors).

## Decisions

### Decision: New `scripts/seed_demo.py` (package `scripts/seed_demo/`) that calls the existing `seed()`
Create a separate entrypoint `poetry run python -m scripts.seed_demo` rather than overloading `scripts.seed`. It first invokes the existing `seed()` (or its `seed_rbac` + tenant/branch/admin helpers) to guarantee the baseline exists, then layers the operational data. **Why over editing `seed.py`:** tests and the documented login flow depend on `scripts.seed` being minimal and fast; keeping the heavy dataset behind a distinct module preserves that contract and makes intent obvious. If the file grows large, split into a `scripts/seed_demo/` package with one module per area (`supplies.py`, `menu.py`, `delivery.py`, …) orchestrated by `__main__.py`.

### Decision: Select-or-create keyed on natural identifiers, single transaction
Each entity is looked up by a stable natural key scoped to the demo tenant/branch (tenant slug, branch code, ingredient name, unit abbreviation, route name, customer email, product+variant name) before insert, mirroring the pattern already in `seed.py`. All work happens inside one `async with SessionFactory() as session:` with `flush()` between dependency layers and a single `commit()` at the end. **Why:** idempotency without duplicates; a single transaction keeps the dataset all-or-nothing so a partial failure never leaves a half-seeded demo.

### Decision: Explicit layered ordering helper functions
One `async def seed_<area>(session, ctx)` helper per area returning the created/looked-up entities (ids) needed downstream, called in FK-safe order: units/countries/cities → tenant/branch (existing) → persons/users/RBAC/employees(drivers) → ingredients(insumos) → inventory_stocks → suppliers/supplier_ingredients → menu (categories/products/variants) → recipe_items → customers → delivery_routes/route_drivers/runs → dining_tables → orders/order_items/order_payments → order_deliveries → cash_session/movements → finance expense. **Why:** matches the RESTRICT FK constraints and keeps each area independently readable/testable.

### Decision: Import `restaurante.shared.models_registry` first
As in `seed.py:20`, import the registry before touching models so all tables (and cross-module FKs) are registered in `Base.metadata`. **Why:** avoids missing-mapper errors for cross-module relationships.

### Decision: Decimals everywhere for money/quantity
Use `decimal.Decimal` literals for all `Numeric` columns (prices, totals, stock, lat/long). **Why:** passing `float` to `Numeric` risks precision drift and, for geo `Numeric(10,7)`, silent rounding.

## Risks / Trade-offs

- **Status string drift** (no DB enum) → Centralize status constants at the top of the seed module and use the conventional values reported by the model audit (`orders=open`, `order_items=pending`, `delivery_runs=preparing`, `order_deliveries=pending`, `cash_sessions=open`, etc.); cross-check against each module's domain entities before writing.
- **Idempotency gaps for child rows** (e.g. order items, route-driver links) → Key children on (parent natural key + child natural key) and guard each insert; verify by running the loader twice in a scratch DB and asserting row counts are stable.
- **Schema drift over time** (columns added later) → Keep helpers small and colocated per area so a future column change touches one function; rely on `mypy`/`ruff` and a smoke run to catch breakage.
- **Accidental cross-tenant writes** → All inserts go through helpers that receive the demo `tenant_id`/`branch_id`; never rely on the ambient tenant filter.
- **Heavier/slower than `seed.py`** → Acceptable; it is opt-in and separate from the test baseline.

## Migration Plan

1. Apply migrations: `poetry run alembic upgrade head`.
2. Run baseline (idempotent): handled automatically by the demo loader calling `seed()`.
3. Run `poetry run python -m scripts.seed_demo` to load the demo dataset.
4. **Reset**: drop/recreate the schema (`alembic downgrade base && alembic upgrade head`) or truncate demo tables, then re-run — documented in `backend/CLAUDE.md`. No rollback of code needed; the loader writes data only.
5. Validate with `poetry run ruff check .` and `poetry run mypy src`, plus a smoke run asserting non-empty inventory and delivery routes.

## Open Questions

- Volume of sample orders/deliveries — default to a small but report-meaningful set (≈5–10 orders, 2 routes, 2–3 drivers); confirm if the live demo needs more.
- Whether to add a `--reset` flag to the loader (truncate demo data first) or keep reset as a documented manual step. Default: documented manual step for the first version.
