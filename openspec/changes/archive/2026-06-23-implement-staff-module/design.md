## Context

The `staff` module has ORM models (`employees`, `planned_shifts`, `attendances`, `commissions` in `infrastructure/models.py`) and domain dataclasses, but no functional layer. The `menu` and `identity` modules are the established reference for a complete hexagonal module in this codebase. This design adds the staff application + API layer by mirroring those references rather than inventing new patterns. The driving constraints (from `CLAUDE.md`): hexagonal layering (`API → application → domain`; `infrastructure` implements ports), row-level multi-tenancy by `tenant_id`, multi-branch readiness via `branch_id`, and English-only identifiers.

Key facts confirmed against the codebase:
- `tenant_id` is resolved by subdomain middleware and exposed via `shared/api/deps.get_tenant_id`. There is **no** branch middleware — `branch_id` is passed explicitly and validated against the tenant (same approach `menu` uses for branch-scoped prices).
- An automatic tenant filter exists in `shared/tenancy/filtering.py`; repos still filter explicitly as defense-in-depth (matching `menu`).
- Permissions `staff.read` and `staff.manage` already exist in `identity/domain/permissions_catalog.py` and are enforced via `require_permission(code)` used as a FastAPI route dependency.
- `staff` is already registered in `shared/models_registry.py`, so Alembic autogenerate sees it.

## Goals / Non-Goals

**Goals:**
- Implement domain ports, an application service, a SQLAlchemy repository, and an API router for staff, mirroring `menu`.
- Full tenant isolation and branch validation on every operation.
- RBAC enforcement (`staff.read` / `staff.manage`).
- Integration tests following the menu test suite pattern (sqlite, FK enforcement on).

**Non-Goals:**
- Payroll calculation, commission auto-generation from orders (only manual commission entry), or scheduling/rostering optimization.
- Driver-specific delivery logic (lives in the `delivery` module, which will reference employees later).
- Any change to the existing table structure unless a constraint gap is found during implementation; no speculative migration.

## Decisions

**1. Mirror the `menu` module layout exactly.**
`domain/ports.py` (a `Protocol` named `StaffRepository`), `application/use_cases/manage_staff.py` (`StaffService` taking the repo in its constructor), `infrastructure/repositories.py` (`SqlAlchemyStaffRepository(session)`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency lowers review cost and matches the layering rule. Alternative (a leaner single-file service) rejected — it would diverge from the only working reference.

**2. `branch_id` passed explicitly and validated, not resolved from context.**
Employee/shift writes take `branch_id` in the request body and the service calls a `branch_exists(tenant_id, branch_id)` check before persisting (exactly like `menu.set_price`). Rationale: no branch middleware exists; explicit + validated avoids silent cross-branch writes. Alternative (infer single branch) rejected — violates the "designed for N branches from day one" decision.

**3. Validation split: Pydantic for shape, service for business rules.**
Pydantic v2 schemas enforce types and simple constraints (positive amount, time/datetime presence). The service enforces cross-entity rules: reference existence (person/user/role/branch/employee), uniqueness of person_id/user_id, `end_time > start_time`, `check_out_at > check_in_at`, and the single-open-attendance invariant. Rationale: keep the domain framework-free while giving fast 422s for malformed input.

**4. Errors reuse `shared/domain/errors`.**
`NotFoundError` for missing references/records (→404), `ConflictError` for duplicates and the second-open-attendance case (→409), `ValidationError`/422 for shape. These already have HTTP mappings registered (per the menu module). No new exception types.

**5. Commit per write (atomic admin actions), map `IntegrityError` → `ConflictError`.**
Matches the menu repository. Uniqueness on `person_id`/`user_id` is enforced both by a pre-check (clear error message) and by catching the DB `IntegrityError` (race safety).

## Risks / Trade-offs

- **Pre-check + DB-constraint duplication for uniqueness** → Accept: pre-check gives a friendly message, the constraint guarantees correctness under concurrency.
- **Single-open-attendance invariant is checked in application code, not the DB** → A concurrent double check-in could theoretically create two open attendances. Mitigation: low real-world likelihood (one device per employee clock-in); revisit with a partial unique index if it becomes a problem. Logged as an open question rather than over-engineered now.
- **No branch middleware means every branch-scoped endpoint must remember to validate `branch_id`** → Mitigation: centralize the check in the service (`_require_branch`) so routers can't forget it.
- **sqlite tests vs Postgres prod** → Tests enable FK enforcement (the menu suite already does this); behavior for `Numeric`/`Time` types is consistent enough for these rules.

## Migration Plan

1. No schema change expected. After implementation, run `alembic revision --autogenerate` to confirm a **no-op** diff (proves models and DB agree). If a needed constraint is missing (e.g., a unique index), include it in that migration.
2. Deploy is additive — new endpoints under `/staff`, router included in `main.py`. No rollback of data required; reverting the code removes the endpoints.

## Open Questions

- Should the single-open-attendance rule be hardened with a DB partial unique index now, or deferred? (Default: defer.)
- Do planned shifts need overlap detection (two shifts same employee/day)? Spec currently does not require it; defer unless a pilot needs it.
