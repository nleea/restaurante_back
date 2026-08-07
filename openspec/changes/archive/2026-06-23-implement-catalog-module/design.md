## Context

The `catalog` module has 3 ORM tables — `countries`, `cities`, `units_of_measure` — all using plain `Base` (no tenancy mixin, no automatic tenant filter): they are global reference data shared by all tenants. `units_of_measure` is already consumed by `recipes` and `purchasing` but has no API. Constraints from `CLAUDE.md`: hexagonal layering, English identifiers, "small complete system". Note the tenancy rule is row-level `tenant_id` for *business* entities; these are deliberately global catalogs, an explicit exception in the data model.

Facts confirmed in code:
- `countries`: `name`, unique `iso_code`. `cities`: `country_id` (FK), `name`, `state_province`. `units_of_measure`: `name`, `abbreviation`, self-referential `base_unit_id`, `conversion_factor`.
- **No `catalog.*` permissions exist** → must be added to `identity/domain/permissions_catalog.py`. `admin` = all codes, so it inherits them.
- Entities violate the convention (`id` required first) → restructure.
- `catalog` is registered in `models_registry.py`; tables in migration `0002`. Shared `ValidationError` (→422) exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, API router for countries, cities, and units of measure.
- Add `catalog.read` / `catalog.manage` permissions; enforce RBAC.
- Reference validation (city→country, unit→base unit) and unit base/factor rules.
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Restricting catalog writes to a platform-admin tier (no such tier exists in RBAC yet).
- Actual unit conversion math in recipes/inventory/purchasing (costing change).
- Bulk seeding of standard countries/units.

## Decisions

**1. Mirror the established layout; one `CatalogService`.**
`domain/ports.py` (`CatalogRepository`), `application/use_cases/manage_catalog.py` (`CatalogService`), `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`.

**2. Global data — no tenant filtering, but RBAC still applies.**
The repository queries the catalog tables without a `tenant_id` filter (they have none). The API still depends on the authenticated context and `require_permission`, so only authorized users read/write. Rationale: these are shared catalogs by design; tenancy would be wrong here. The cross-tenant write-authority concern (a tenant admin editing global data) is acknowledged and deferred — gating by `catalog.manage` is the available control today.

**3. New permissions added to the central catalog.**
Add `catalog.read` / `catalog.manage` to `PERMISSIONS`. `admin` inherits them automatically; no base-role list edits. Rationale: keeps the catalog the single source of truth (same approach used when `recipes` introduced its permissions).

**4. Unit base/factor integrity enforced in the service.**
`base_unit_id` and `conversion_factor` must be set together or both null; factor must be positive; the referenced base unit must exist; on update a unit cannot reference itself. Rationale: keeps the conversion graph sane even though conversion math is out of scope; cheap invariants now prevent bad data later.

**5. Validation split: Pydantic for shape, service for cross-entity rules.**
Pydantic: required name/abbreviation/iso_code, optional base/factor, factor `> 0` when present. Service: ISO-code uniqueness (also DB-enforced → `ConflictError`), country existence for cities, base-unit existence and the base/factor/self-reference rules. Errors reuse `shared/domain/errors`.

## Risks / Trade-offs

- **Any tenant admin can edit global catalogs** → real risk of cross-tenant interference; mitigated only by `catalog.manage` assignment today. Documented as an open question pending a platform-admin tier.
- **Unique `iso_code` is global** → two tenants can't both define the same country code differently; that is the intended shared-catalog behavior.
- **No conversion math** → `conversion_factor` is stored but not applied; consistent with the rest of the system (documented).
- **sqlite vs Postgres** → unique/self-ref FK constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all three tables exist in migration `0002`. Autogenerate should be a no-op (verify statically if Postgres unavailable).
2. Adding permission rows is data, upserted idempotently by `seed_rbac`.
3. Deploy is additive — new `/catalog` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should catalog writes require a future platform-admin role rather than tenant `catalog.manage`? (Default: tenant `catalog.manage` now; revisit with a platform tier.)
- Should countries/units be bulk-seeded with sensible defaults on tenant creation? (Default: out of scope; separate seed.)
