## Context

The `inventory` module has ORM models (`inventory_stocks`, `inventory_movements`) and domain dataclasses but no functional layer. The `menu` and `staff` modules are the established hexagonal reference. This change adds the inventory application + API layer by mirroring them. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy by `tenant_id`, multi-branch via `branch_id` on every business entity, English-only identifiers.

Facts confirmed in code:
- `tenant_id` comes from the subdomain middleware (`shared/api/deps.get_tenant_id`); there is no branch middleware, so `branch_id` is explicit and validated (as `menu`/`staff` do).
- Both inventory tables use `BranchScopedMixin` (tenant_id + branch_id, auto-filtered).
- `inventory_stocks` has a unique constraint on `(ingredient_id, branch_id)`.
- `inventory_movements` requires `employee_id` (FK to `employees`, RESTRICT) and `ingredient_id` (FK to `ingredients`, RESTRICT). `ingredients` is owned by the data-only `recipes` module and is tenant-scoped (`IngredientModel`: id, name, unit_of_measure_id, is_active).
- Permissions `inventory.read` / `inventory.adjust` already exist and are enforced via `require_permission(code)`.
- `inventory` is already registered in `shared/models_registry.py`.
- A shared `ValidationError` (→422) now exists (added with the staff module).

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for inventory, mirroring `staff`.
- Stock changes are always recorded as movements and applied to the stock row atomically.
- Tenant isolation, branch validation, and cross-module reference validation (`ingredient_id`, `employee_id`).
- RBAC enforcement (`inventory.read` / `inventory.adjust`).
- Integration tests following the staff suite (sqlite, FK enforcement on).

**Non-Goals:**
- Automatic stock deduction from sales (that is the recipes↔orders integration, a later change).
- Purchase receiving workflows (purchasing module) — inventory only exposes a generic `in` movement that purchasing will later call.
- Unit-of-measure conversions, valuation/costing, or multi-warehouse-within-a-branch.

## Decisions

**1. Mirror the `staff` module layout exactly.**
`domain/ports.py` (`InventoryRepository` Protocol), `application/use_cases/manage_inventory.py` (`InventoryService`), `infrastructure/repositories.py` (`SqlAlchemyInventoryRepository(session)`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency with the only two working references lowers review cost.

**2. Movements are the single source of truth; stock is a derived cache updated in the same transaction.**
Every stock-changing operation (`in`, `out`, `adjustment`) writes a movement row AND updates the `inventory_stocks` row, committing once. Rationale: keeps an honest audit trail (the `inventory_movements` table exists precisely for this) and prevents stock drift. The repository performs the read-modify-write of the stock row plus the movement insert before a single `commit()`. Alternative (separate endpoints that edit stock directly without a movement) rejected — it would allow untraceable stock edits.

**3. Stock row auto-created on first movement / first threshold set.**
There is no separate "create stock line" step; the first `in` movement (or `set_min_stock`) upserts the row (on-hand 0 + delta). Rationale: matches real usage (first purchase starts tracking) and avoids a redundant admin step. The `(ingredient_id, branch_id)` unique constraint guarantees one row.

**4. Movement direction model: `type` ∈ {in, out, adjustment}, `quantity` positive magnitude.**
`in` adds, `out` subtracts (rejected if it would go negative → `ConflictError`), `adjustment` is produced only by the recount operation which computes `counted - current` and stores its magnitude with the appropriate type. Rationale: the model stores `quantity` as unsigned `Numeric`; encoding direction in `type` keeps the ledger readable and avoids signed-quantity ambiguity. The recount endpoint is the safe, user-facing way to correct counts (physical inventory / arqueo).

**5. Reference validation split: Pydantic for shape, service for cross-entity rules.**
Pydantic enforces positive quantity / non-negative threshold and required fields (fast 422). The service validates branch/ingredient/employee existence within the tenant and the no-negative-stock invariant. Errors reuse `shared/domain/errors`: `NotFoundError`→404, `ConflictError`→409, `ValidationError`→422.

**6. `employee_id` passed explicitly (validated), not inferred.**
Like `menu`/`staff` pass `branch_id`, the movement endpoints take `employee_id` in the body and validate it belongs to the tenant. Rationale: no actor→employee resolution exists yet; orders will pass it automatically later.

## Risks / Trade-offs

- **Concurrent movements on the same stock row** could race the read-modify-write and lose an update or momentarily allow an over-draw. → For pilot scale (one POS per branch) this is acceptable; a follow-up can add `SELECT ... FOR UPDATE` (Postgres) or an atomic `UPDATE ... SET qty = qty + :d WHERE qty + :d >= 0`. Logged as an open question, not over-engineered now.
- **`adjustment` quantity loses sign** (stored as magnitude) → the resulting on-hand is authoritative and the previous value is recoverable from history; acceptable.
- **sqlite tests vs Postgres** → `Numeric` arithmetic is consistent for these rules; FK enforcement is enabled in tests (as in the staff suite).

## Migration Plan

1. No schema change expected. After implementation, an `alembic revision --autogenerate` should be a no-op for inventory (tables already in migration `0002`). Live run needs Postgres; if unavailable, verify model↔migration alignment statically (as done for staff).
2. Deploy is additive — new `/inventory` endpoints, router included in `main.py`. Reverting the code removes the endpoints; no data migration.

## Open Questions

- Harden concurrency with row locking / atomic conditional update now, or defer? (Default: defer to a follow-up.)
- Should `out` movements be allowed to drive negative on-hand with an explicit override flag for edge cases? (Default: no — reject; recount is the correction path.)
