## Context

The `recipes` module has ORM models (`ingredients`, `recipe_items`) and domain dataclasses but no functional layer. The `menu`/`staff`/`inventory` modules are the established hexagonal reference; this change mirrors them. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy by `tenant_id`, English-only identifiers, and the binding decision that **Recipes is foundational, not a nice-to-have** — it is the only link between sales and stock.

Facts confirmed in code:
- `ingredients` and `recipe_items` are **tenant-scoped** (`TenantScopedMixin`), not branch-scoped — a recipe definition is shared across branches. (Stock, which IS branch-specific, lives in `inventory`.)
- `recipe_items` references `product_variants` (owned by `menu`, data-only) and `units_of_measure` (owned by `catalog`, data-only, global / not tenant-scoped). `ingredients` references `units_of_measure`.
- `recipe_items` has a unique constraint on `(product_variant_id, ingredient_id)`.
- The entities already follow the project convention (business fields first, `id` optional).
- **No `recipes.*` permissions exist yet** — they must be added to `identity/domain/permissions_catalog.py`. The `admin` base role is `set(ALL_PERMISSION_CODES)` (derived from the `PERMISSIONS` tuple), so it picks up new codes automatically.
- `recipes` is already registered in `shared/models_registry.py`.
- Shared `ValidationError` (→422) already exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for recipes, mirroring `inventory`.
- Full CRUD for **ingredients** (the table inventory already depends on).
- Per-variant **BOM** management: add/list/update/remove recipe lines.
- Tenant isolation + cross-module reference validation (`product_variant_id`, `ingredient_id`, `unit_of_measure_id`).
- Add `recipes.read` / `recipes.manage` to the permissions catalog.
- Integration tests following the inventory suite (sqlite, FK enforcement on).

**Non-Goals:**
- Creating/materializing `product_variants` (that lifecycle belongs to `menu`'s deferred variant work). Recipes only validates a variant exists.
- Cost rollup / margin computation (needs ingredient costs from `purchasing`; a later change).
- Inventory deduction on sale (the `orders` → recipes → inventory integration; a later change).
- Unit-of-measure conversion between a recipe line's unit and the ingredient's base unit.

## Decisions

**1. Mirror the `inventory` module layout exactly.**
`domain/ports.py` (`RecipesRepository` Protocol), `application/use_cases/manage_recipes.py` (`RecipesService`), `infrastructure/repositories.py` (`SqlAlchemyRecipesRepository(session)`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency with the three working references.

**2. Recipes owns `ingredients`; references everything else read-only.**
The service exposes full ingredient CRUD but only *validates* `product_variant_id` and `unit_of_measure_id` against their owner tables (`menu`, `catalog`). Rationale: respects module ownership (the layering rule) and matches how `inventory` validates `ingredient_id` without owning it. This also closes the gap inventory left open (inventory referenced `ingredients` with no way to create them — now there is one).

**3. BOM is addressed per variant; lines are managed individually.**
Write endpoints: `POST /recipes/variants/{variant_id}/items` (add line), `GET /recipes/variants/{variant_id}/items` (full recipe), `PATCH /recipes/items/{item_id}` (quantity/unit), `DELETE /recipes/items/{item_id}`. Rationale: mirrors menu's variant-group/option addressing and keeps each line independently editable. The unique `(product_variant_id, ingredient_id)` constraint is enforced by a service pre-check (friendly message) plus the DB constraint (race safety) → `ConflictError`.

**4. Validation split: Pydantic for shape, service for cross-entity rules.**
Pydantic enforces positive `quantity` and required fields (fast 422). The service validates reference existence within the tenant (variant, ingredient) or globally (unit), uniqueness, and re-checks quantity. Errors reuse `shared/domain/errors`: `NotFoundError`→404, `ConflictError`→409, `ValidationError`→422.

**5. New permissions added to the central catalog.**
Add `_p("recipes.read", …, "recipes", …)` and `_p("recipes.manage", …, "recipes", …)` to `PERMISSIONS`. `admin` inherits them automatically; no base-role list edits required. Rationale: keeps the catalog the single source of truth and is the first module to introduce its own permission codes.

## Risks / Trade-offs

- **No way to create `product_variants` yet** → a real end-user cannot fully build a recipe through the API until `menu` exposes variant materialization. → Accept: that work is explicitly `menu`'s; recipes is testable with seeded variants now, and orders depends on recipes existing first. Mirrors the inventory→ingredients ordering we already used.
- **Mixed-unit recipe lines** (line unit ≠ ingredient base unit) are stored as-is without conversion → Accept for now; conversion belongs with costing. The `units_of_measure` table already carries `base_unit_id`/`conversion_factor` for a later change.
- **sqlite tests vs Postgres** → `Numeric` arithmetic and FK/unique constraints behave consistently for these rules; FK enforcement is enabled in tests.

## Migration Plan

1. No schema change expected. After implementation, an `alembic revision --autogenerate` should be a no-op for recipes (tables already in migration `0002`). Live run needs Postgres; if unavailable, verify model↔migration alignment statically.
2. Adding permission rows is data, not schema: they are upserted idempotently by `seed_rbac` on the next seed/run; existing tenants gain the codes when reseeded.
3. Deploy is additive — new `/recipes` endpoints, router included in `main.py`. Reverting the code removes the endpoints.

## Open Questions

- Should an ingredient deactivation be blocked when it is used by an active recipe line, or allowed (soft)? (Default: allow; the FK is RESTRICT only on hard delete, and we deactivate rather than delete.)
- Should recipes expose a minimal "create default variant for a product" helper to bridge the menu gap, or wait for menu? (Default: wait for menu to keep ownership clean.)
