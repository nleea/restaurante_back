## 1. RBAC permission

- [x] 1.1 Add `audit.read` to `PERMISSIONS` in `identity/domain/permissions_catalog.py` (module `audit`). Confirm `admin` picks it up; no base-role edits needed.

## 2. Domain layer

- [x] 2.1 Create `modules/audit/domain/entities.py` with an `AuditLogEntry` dataclass mirroring `AuditLogModel` (id, tenant_id, actor_id, branch_id, action, entity_type, entity_id, ip, detail, created_at) — convention-compliant.
- [x] 2.2 Create `modules/audit/domain/ports.py` with an `AuditQueryRepository` `Protocol`: `list_entries(tenant_id, *, action=None, actor_id=None, entity_type=None, entity_id=None, branch_id=None, limit, offset)` and `get_entry(tenant_id, entry_id)`.

## 3. Infrastructure — repository

- [x] 3.1 Create `modules/audit/infrastructure/repositories.py` with `SqlAlchemyAuditQueryRepository(session)` reading `shared.audit.models.AuditLogModel`; filter explicitly by `tenant_id`. Add an ORM→`AuditLogEntry` mapper.
- [x] 3.2 Implement `list_entries`: apply optional filters; `action` matches exact OR dotted-prefix (`action == v OR action LIKE v || '.%'`); order by `created_at` desc; apply `limit`/`offset`. Implement `get_entry`.

## 4. Application — service

- [x] 4.1 Create `modules/audit/application/use_cases/query_audit.py` with `AuditQueryService(repo)`.
- [x] 4.2 `list_entries`: clamp `limit` to a max (e.g. 200, default 50), non-negative `offset`; pass filters through. `get_entry`: raise `NotFoundError` when missing.

## 5. API layer

- [x] 5.1 Create `modules/audit/infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_audit_service`, `AuditServiceDep`).
- [x] 5.2 Create `modules/audit/infrastructure/api/schemas.py` with an `AuditLogEntryResponse` Pydantic model (read-only).
- [x] 5.3 Create `modules/audit/infrastructure/api/router.py` with `APIRouter(prefix="/audit", tags=["audit"])`, all endpoints gated by `Depends(require_permission("audit.read"))`: `GET /audit/logs` (query params: action, actor_id, entity_type, entity_id, branch_id, limit, offset) and `GET /audit/logs/{entry_id}`. No write endpoints.
- [x] 5.4 Register `audit_router` in `src/restaurante/main.py` (import + `app.include_router`). Add the missing `__init__.py` files for the new `modules/audit` packages.

## 6. Verification

- [x] 6.1 Confirm alembic alignment: no schema change (table in `0001`); permission is data.
- [x] 6.2 Write integration tests under `tests/modules/audit/` (sqlite) covering: tenant isolation (cross-tenant 404 + list excludes other tenant); list newest-first; filter by action prefix (`login` matches `login.success`/`login.failure`) and by actor; pagination (limit clamp + offset); get by id; read-only (no create/update/delete routes); RBAC 403 without `audit.read`. Seed rows via `SqlAlchemyAuditRecorder` / `AuditLogModel` directly.
- [x] 6.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 6.4 Smoke-check `/audit` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (audit query implemented; recording already existed).
