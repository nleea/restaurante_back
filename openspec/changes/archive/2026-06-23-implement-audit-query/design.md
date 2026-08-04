## Context

Auditing is a cross-cutting capability already half-built: `shared/audit/models.py` (`AuditLogModel`, tenant-scoped, optional `branch_id`, `action`, `actor_id`, `entity_type`/`entity_id`, `ip`, `detail`, timestamps), `shared/domain/audit.py` (`AuditEvent` + `AuditEventRecorder` Protocol), and `shared/audit/recorder.py` (`SqlAlchemyAuditRecorder`, own session, fault-tolerant) used by identity login. The table is in migration `0001`. What is missing is the **read** side and an `audit.read` permission. Constraints from `CLAUDE.md`: hexagonal layering, row-level tenancy, English identifiers; auditing is explicitly cross-cutting.

Facts confirmed in code:
- `AuditLogModel` is tenant-scoped (auto tenant filter applies) with a nullable `branch_id`.
- No `audit.*` permission exists → must be added.
- Recording works and is unchanged by this change.

## Goals / Non-Goals

**Goals:**
- A read-only query API over the existing audit log: list with filters + pagination, get by id.
- Add `audit.read`; enforce RBAC and tenant isolation.
- Integration tests.

**Non-Goals (deferred):**
- Instrumenting more write paths (orders/cash/purchasing/...) to emit events — incremental future work; the recorder is ready.
- Retention/archival/export and tamper-evidence (signing/hash-chain).
- Any mutation of audit entries.

## Decisions

**1. A thin read-only `modules/audit` over the shared model.**
Recording stays in `shared/audit` (cross-cutting). The query side follows the established module shape — `domain/entities.py` (`AuditLogEntry`), `domain/ports.py` (`AuditQueryRepository`), `application/use_cases/query_audit.py` (`AuditQueryService`), `infrastructure/{repositories,api}` — but its repository reads the existing `shared.audit.models.AuditLogModel`. Rationale: every HTTP surface in this codebase is a module router registered in `main.py`; mirroring that keeps tests/routers uniform, while the model/recorder remain in their cross-cutting home.

**2. Read-only by construction.**
The module exposes only `list` and `get`; there is no create/update/delete. Writing remains exclusively the recorder's job, preserving an append-only, system-authored trail. Rationale: an editable audit log is worthless; immutability is the point.

**3. Action filtering supports exact and dotted-prefix match.**
`action` filter matches either the exact value or a prefix on the dotted verb (`login` → `login.success`, `login.failure`). Implemented as `action == value OR action LIKE value || '.%'`. Rationale: events use a dotted taxonomy; auditors filter by family (`login`, `orders`, ...) or exact event.

**4. Pagination with a clamped maximum.**
`limit` defaults (e.g. 50) and is clamped to a maximum (e.g. 200); `offset` for paging. Rationale: the audit log grows unbounded; never return it all.

**5. Tenant isolation belt-and-suspenders.**
The repository filters `tenant_id` explicitly (in addition to the automatic tenant filter), consistent with every other module.

**6. New permission in the central catalog.**
Add `audit.read` to `PERMISSIONS`; `admin` inherits it. Rationale: same single-source-of-truth approach used when recipes/catalog introduced permissions. (No `audit.manage` — nothing to manage.)

## Risks / Trade-offs

- **Coupling the audit module to the shared model's shape** → acceptable: the model is stable and the module is explicitly its reader; no schema ownership is taken.
- **Sparse data until more paths are instrumented** → today mostly login events exist; the query API still works and grows as instrumentation lands. Documented.
- **`detail` free-text** is returned as-is → the recorder is responsible for keeping it non-sensitive (no passwords/tokens); the reader does not transform it.
- **sqlite vs Postgres** → `LIKE`-prefix and ordering behave consistently for these queries; tests run on sqlite.

## Migration Plan

1. No schema change — `audit_logs` exists in migration `0001`. Adding `audit.read` is data, upserted by `seed_rbac`.
2. Deploy is additive — new read-only `/audit` endpoints, router in `main.py`. Reverting removes the read API; recording is untouched.

## Open Questions

- Should a date-range filter (`from`/`to` on `created_at`) be added now? (Default: ship the core filters + pagination; date range is a cheap follow-up.)
- Should `audit.read` be platform-admin-only rather than a tenant permission? (Default: tenant `audit.read`; entries are already tenant-scoped, so a tenant sees only its own trail.)
