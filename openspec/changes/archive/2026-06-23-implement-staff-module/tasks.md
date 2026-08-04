## 1. Domain layer

- [x] 1.1 Review `domain/entities.py`; ensure dataclasses exist for `Employee`, `PlannedShift`, `Attendance`, `Commission` with all fields (incl. `tenant_id`, and `branch_id` for `Employee`/`PlannedShift`). Add any missing ones, framework-free.
- [x] 1.2 Create `domain/ports.py` with a `StaffRepository` `Protocol` covering: branch existence check; person/user/role existence checks; employee create/get/list/update/deactivate; planned shift create/get/list/update/delete; attendance create (check-in)/get/list/find-open/set-check-out; commission create/list. All read methods take `tenant_id` and return entity-or-`None`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyStaffRepository(session: AsyncSession)` implementing `StaffRepository`, filtering every query explicitly by `tenant_id` (and `branch_id` where applicable).
- [x] 2.2 Implement reference-existence helpers (`branch_exists`, `person_exists`, `user_exists`, `role_exists`) querying the respective tables scoped by tenant.
- [x] 2.3 Add ORM→entity mapper functions; commit per write; catch `IntegrityError` and raise `ConflictError`.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_staff.py` with `StaffService(repo)`; add private `_require_employee` and `_require_branch` helpers raising `NotFoundError`.
- [x] 3.2 Implement employee use cases: create (validate person/user/role/branch exist; enforce unique person_id/user_id → `ConflictError`), list, get, update role, deactivate.
- [x] 3.3 Implement planned-shift use cases: create/list/update/delete; enforce `end_time > start_time` and employee existence.
- [x] 3.4 Implement attendance use cases: check-in (reject if an open attendance exists → `ConflictError`), check-out (enforce `check_out_at > check_in_at`), list.
- [x] 3.5 Implement commission use cases: create (positive amount), list by employee.

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep` via `get_tenant_id`, `get_staff_service`, `StaffServiceDep`) mirroring `menu/.../deps.py`.
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 request/response models for employees, shifts, attendances, commissions (positive-amount and required-field validators).
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/staff", tags=["staff"])`; reads use `Depends(require_permission("staff.read"))`, writes use `Depends(require_permission("staff.manage"))`. Endpoints for employees, shifts, attendances, commissions.
- [x] 4.4 Register `staff_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Run `poetry run alembic revision --autogenerate -m "staff"` and confirm a no-op diff (models match DB); if a constraint is missing, keep only that change in the migration.
- [x] 5.2 Write integration tests under `tests/` (sqlite, FK enforcement on) covering: tenant isolation, cross-tenant 404, branch validation, employee CRUD + duplicate conflict, shift time validation, attendance single-open invariant + check-out validation, commission positive-amount, and RBAC 403 for read/write without permission.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Manually verify `/staff` endpoints appear in OpenAPI and enforce permissions (smoke check against the seeded demo tenant).
