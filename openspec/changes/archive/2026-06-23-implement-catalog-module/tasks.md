## 1. RBAC permissions

- [x] 1.1 Add `catalog.read` and `catalog.manage` to `PERMISSIONS` in `identity/domain/permissions_catalog.py` (module `catalog`). Confirm `admin` picks them up; no base-role edits needed.

## 2. Domain layer

- [x] 2.1 Restructure `domain/entities.py` to the convention (business fields first; `id` optional; `state_province`/`base_unit_id`/`conversion_factor` optional) for `Country`, `City`, `UnitOfMeasure`.
- [x] 2.2 Create `domain/ports.py` with a `CatalogRepository` `Protocol`: country create/get/list/update + `iso_code_exists`; city create/get/list(filter country)/update + `country_exists`; unit create/get/list/update + `unit_exists`. (No `tenant_id` params — global data.)

## 3. Infrastructure — repository

- [x] 3.1 Create `infrastructure/repositories.py` with `SqlAlchemyCatalogRepository(session)` implementing the port (no tenant filtering — catalog tables are global). Add ORM→entity mappers.
- [x] 3.2 Countries: create → catch unique `iso_code` → `ConflictError`; get; list; update. `iso_code_exists`.
- [x] 3.3 Cities: create; get; list (filter country); update. `country_exists`. Units: create; get; list; update. `unit_exists`.

## 4. Application — service

- [x] 4.1 Create `application/use_cases/manage_catalog.py` with `CatalogService(repo)` and guards `_require_country`, `_require_unit`.
- [x] 4.2 Countries: create (duplicate iso → `ConflictError`), list, get, update.
- [x] 4.3 Cities: create (validate country), list (filter country), get, update.
- [x] 4.4 Units: create/update with the base/factor rules — both set or both null (`ValidationError`); positive factor; base unit must exist (`NotFoundError`); a unit cannot be its own base (`ValidationError`); list, get.

## 5. API layer

- [x] 5.1 Create `infrastructure/api/deps.py` (`SessionDep`, `get_catalog_service`, `CatalogServiceDep`; include `TenantDep` only to enforce an authenticated context).
- [x] 5.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: country create/update; city create/update; unit create/update (optional base_unit_id + conversion_factor `gt=0`); responses for country, city, unit.
- [x] 5.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/catalog", tags=["catalog"])`. Permission deps: read=`catalog.read`, manage=`catalog.manage`. Endpoints: countries create/list/get/update; cities create/list(filter country)/get/update; units create/list/get/update.
- [x] 5.4 Register `catalog_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 6. Verification

- [x] 6.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 6.2 Write integration tests under `tests/modules/catalog/` (sqlite, FK enforcement on) covering: country create + duplicate-iso 409; city create + unknown-country 404 + list by country; unit create base + derived (base/factor) + base/factor mismatch 422 + unknown-base 404 + self-reference 422 on update; RBAC 403 for read/manage; data is visible across tenants (global). Authenticate via the demo tenant.
- [x] 6.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 6.4 Smoke-check `/catalog` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (catalog implemented).
