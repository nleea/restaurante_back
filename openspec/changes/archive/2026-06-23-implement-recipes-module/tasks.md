## 1. RBAC permissions

- [x] 1.1 Add `recipes.read` and `recipes.manage` to `PERMISSIONS` in `identity/domain/permissions_catalog.py` (module `recipes`). Confirm `admin` (= all codes) picks them up; no base-role edits needed.

## 2. Domain layer

- [x] 2.1 Review `domain/entities.py`; confirm `Ingredient` and `RecipeItem` follow the convention (business fields first, `id` optional). Adjust only if needed.
- [x] 2.2 Create `domain/ports.py` with a `RecipesRepository` `Protocol`: unit/variant existence checks; ingredient create/get/list/update; recipe-item add/get/list-by-variant/update/delete; `recipe_item_exists(variant_id, ingredient_id)`. Reads take `tenant_id` and return entity-or-`None`.

## 3. Infrastructure — repository

- [x] 3.1 Create `infrastructure/repositories.py` with `SqlAlchemyRecipesRepository(session)` implementing `RecipesRepository`, filtering every query explicitly by `tenant_id`.
- [x] 3.2 Implement existence helpers: `unit_exists` (query `UnitOfMeasureModel` by id — global), `variant_exists` (query `ProductVariantModel` scoped by tenant). Add ORM→entity mappers.
- [x] 3.3 Implement ingredient methods (create/get/list with active filter/update) and recipe-item methods (add → catch `IntegrityError`→`ConflictError`; get; list by variant; update; delete).

## 4. Application — service

- [x] 4.1 Create `application/use_cases/manage_recipes.py` with `RecipesService(repo)` and guards `_require_ingredient`, `_require_unit`, `_require_variant`, `_require_recipe_item` raising `NotFoundError`.
- [x] 4.2 Implement ingredient use cases: create (validate unit), list (active filter), get, update (validate unit if present), deactivate.
- [x] 4.3 Implement BOM use cases: add line (validate variant/ingredient/unit; quantity>0 → else `ValidationError`; duplicate ingredient → `ConflictError`), list by variant, update line (quantity>0, validate unit if present), delete line.

## 5. API layer

- [x] 5.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_recipes_service`, `RecipesServiceDep`) mirroring `inventory/.../deps.py`.
- [x] 5.2 Create `infrastructure/api/schemas.py` with Pydantic v2 request/response models for ingredients and recipe items (positive-quantity validator, required fields).
- [x] 5.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/recipes", tags=["recipes"])`; reads use `Depends(require_permission("recipes.read"))`, writes use `Depends(require_permission("recipes.manage"))`. Endpoints: ingredients CRUD; variant recipe add/list; recipe-item update/delete.
- [x] 5.4 Register `recipes_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 6. Verification

- [x] 6.1 Confirm alembic alignment: run `alembic revision --autogenerate` if Postgres is available (expect no-op); otherwise verify model↔migration statically for `ingredients`/`recipe_items`.
- [x] 6.2 Write integration tests under `tests/modules/recipes/` (sqlite, FK enforcement on) covering: tenant isolation, cross-tenant 404, ingredient CRUD + unknown-unit 404, BOM add + duplicate 409 + non-positive 422 + unknown variant/ingredient/unit 404, list/update/delete recipe lines, and RBAC 403 for read/write. Add helpers that seed a `unit_of_measure` and a `product_variant` directly (menu has no variant API yet).
- [x] 6.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 6.4 Smoke-check `/recipes` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` to mark recipes implemented.
