## Why

Recipes / Costeo (BOM) is the **critical hinge** of the product: it is the only link between "what I sell" (a product variant / SKU in `menu`) and "what I have in stock" (ingredients tracked by `inventory`). Without it, selling a dish never decrements real inventory and product-level margin can never be computed. The module exists today only as a data layer (`ingredients`, `recipe_items`) with no functional layer. With `inventory` now live (it already consumes the `ingredients` table), implementing recipes closes the loop conceptually and unblocks the future `orders` → inventory-deduction integration. It is the next node on the critical path.

## What Changes

- Add the **application + API layer** for the recipes module, mirroring the `menu`/`staff`/`inventory` reference modules (hexagonal: domain ports → application service → infrastructure repository → API router).
- Expose REST endpoints for **ingredients** (CRUD: create, list, get, update, deactivate) — recipes owns this table, which inventory already references.
- Expose REST endpoints for **recipe items (BOM)** per product variant: add an ingredient line (`ingredient_id`, `quantity`, `unit_of_measure_id`), list the full recipe of a variant, update a line's quantity/unit, and remove a line.
- **Add new RBAC permissions** `recipes.read` and `recipes.manage` to the permissions catalog (they do not exist yet). The base `admin` role (which holds all permissions) picks them up automatically.
- Enforce business rules: ingredient/unit references must exist in scope; a recipe line's `quantity` must be positive; the same ingredient cannot be added twice to one variant (unique `(product_variant_id, ingredient_id)` → conflict).
- Enforce **multi-tenant isolation**: every read/write is scoped to the `tenant_id` from the subdomain middleware. `ingredients` and `recipe_items` are tenant-scoped (not branch-scoped — a recipe is the same across branches). Cross-module references (`product_variant_id` in `menu`, `unit_of_measure_id` in `catalog`) are validated read-only.
- Register the new router in `main.py`.
- No ORM model changes are expected — tables and the `recipes` registration in `models_registry.py` already exist.

## Capabilities

### New Capabilities
- `recipes-management`: Ingredient catalog plus per-variant Bill of Materials (BOM) — the link between sellable variants and stock ingredients, tenant-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/recipes/`: `domain/ports.py`, `application/use_cases/manage_recipes.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`.
- **Modified**: `src/restaurante/modules/identity/domain/permissions_catalog.py` (add `recipes.read` / `recipes.manage`); `src/restaurante/main.py` (include `recipes_router`).
- **Depends on** existing tables `product_variants` (menu, data-only), `units_of_measure` (catalog, data-only), `tenants` — validated for existence; and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **Scope boundary**: this change does NOT create `product_variants` (that lifecycle belongs to `menu`'s deferred variant materialization). Recipes only validates a variant exists; tests seed variants directly. A future `orders` change will use recipes to deduct inventory on sale.
- **APIs**: new `/recipes/*` endpoints. No breaking changes.
- **Tests**: new integration suite under `tests/modules/recipes/` (sqlite, FK enforcement).
