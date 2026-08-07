## Why

The catalog module holds **global reference data shared across all tenants**: countries, cities, and units of measure. `units_of_measure` is already consumed by `recipes` and `purchasing`, but there is no API to create or manage it — today it is seeded directly in tests/fixtures. Without a functional layer, a new deployment cannot populate units, and there is no home for the geographic catalogs (`countries`/`cities`) that `persons`/`tenants` reference. The module exists only as a data layer (3 tables, plain `Base`, no tenancy).

## What Changes

- Add the **application + API layer** for the catalog module (hexagonal).
- **Countries**: CRUD (name, unique ISO code).
- **Cities**: CRUD tied to a country (name, optional state/province); list by country.
- **Units of measure**: CRUD with an optional `base_unit_id` + `conversion_factor` (a non-base unit converts toward its family base, e.g. kg → g factor 1000). List, get, update.
- **Add new RBAC permissions** `catalog.read` and `catalog.manage` to the permissions catalog (they do not exist yet). The base `admin` role picks them up automatically.
- **No tenancy**: catalog tables are global (`Base`, no tenant filter), so reads/writes operate on shared rows. RBAC still applies (a resolved user/tenant is required), and writes are gated by `catalog.manage`.
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `catalog` registration already exist; entities are restructured to the project convention (`id`/optional fields with defaults).

### Explicitly out of scope (deferred)
- **Platform-admin-only restriction on catalog writes** — because catalogs are global, in a mature system only a platform operator (not a tenant admin) should edit them. For now any holder of `catalog.manage` can; tightening this to a platform role is deferred (the RBAC model has no platform-admin tier yet).
- **Unit conversion math** beyond storing `base_unit_id`/`conversion_factor` — actually converting quantities (in recipes/inventory/purchasing) remains a future costing change.
- **Seeding standard countries/units** — this change exposes the API; bulk seed data is separate.

## Capabilities

### New Capabilities
- `catalog-management`: Global reference catalogs — countries, cities, and units of measure — with CRUD and RBAC. Shared across tenants (no row-level tenancy).

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/catalog/`: `domain/ports.py`, `application/use_cases/manage_catalog.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; restructure `domain/entities.py` to the convention.
- **Modified**: `src/restaurante/modules/identity/domain/permissions_catalog.py` (add `catalog.read` / `catalog.manage`); `src/restaurante/main.py` (include `catalog_router`).
- **No cross-module data dependencies** for writes (catalogs are global); `cities` references `countries` and units self-reference — validated internally.
- **Reused**: `shared/api/deps.get_tenant_id` (for the authenticated context), `shared/database.get_session`, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`), RBAC `require_permission`.
- **Closes a gap**: `recipes`/`purchasing` can now reference units created through the API instead of only seeded ones.
- **APIs**: new `/catalog/*` endpoints (countries, cities, units). No breaking changes.
- **Tests**: new integration suite under `tests/modules/catalog/` (sqlite, FK enforcement).
