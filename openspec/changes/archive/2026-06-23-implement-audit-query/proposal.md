## Why

Auditing already **records** events: `shared/audit` has `AuditLogModel` (in migration 0001), the `AuditEvent`/`AuditEventRecorder` port, and a fault-tolerant `SqlAlchemyAuditRecorder` used by identity login. But there is no way to **read** the trail — an admin/auditor cannot answer "who did what, when, from where". This change adds the query side: a read-only, tenant-isolated API over the existing audit log, gated by a new `audit.read` permission. Audit stays append-only and system-recorded; this change exposes visibility, not mutation.

## What Changes

- Add an **audit query module** (`modules/audit`) — a read-only application + API layer over the existing `shared/audit` `AuditLogModel`. Recording infrastructure is unchanged.
- **Query the audit log**: list entries for the current tenant, filterable by `action` (exact or dotted-prefix, e.g. `login`), `actor_id`, `entity_type`, `entity_id`, and `branch_id`, ordered most-recent first, with `limit`/`offset` pagination (sane default/max). Retrieve a single entry by id.
- **Add a new RBAC permission** `audit.read` (it does not exist yet). The base `admin` role picks it up automatically.
- **Read-only**: no create/update/delete endpoints — audit entries are written only by the system recorder and are immutable.
- Enforce **multi-tenant isolation** (entries are tenant-scoped; the automatic tenant filter plus an explicit filter apply).
- Register the new router in `main.py`.
- No ORM model changes and no migration — `audit_logs` already exists. Adding the permission is data (seeded idempotently).

### Explicitly out of scope (deferred)
- **Broader instrumentation** — emitting audit events from more modules (orders, cash, purchasing, etc.). The recorder is ready; wiring each write path is incremental future work, not this change.
- **Retention / archival / export** of audit data.
- **Tamper-evidence** (signing/hash-chaining) of the log.

## Capabilities

### New Capabilities
- `audit-query`: Read-only, tenant-isolated querying of the cross-cutting audit log (filter + paginate), RBAC-protected by `audit.read`.

### Modified Capabilities
<!-- None — recording infrastructure in shared/audit is unchanged. -->

## Impact

- **New code** under `src/restaurante/modules/audit/`: `domain/entities.py` (`AuditLogEntry`) + `domain/ports.py`, `application/use_cases/query_audit.py`, `infrastructure/repositories.py` (reads `shared.audit.models.AuditLogModel`), `infrastructure/api/{deps,schemas,router}.py`.
- **Modified**: `src/restaurante/modules/identity/domain/permissions_catalog.py` (add `audit.read`); `src/restaurante/main.py` (include `audit_router`).
- **Reuses** the existing `AuditLogModel` (shared, already registered + migrated), tenant middleware, `shared/database.get_session`, `shared/domain/errors`, RBAC `require_permission`.
- **APIs**: new read-only `/audit/*` endpoints. No breaking changes; recording behavior untouched.
- **Tests**: new integration suite under `tests/modules/audit/` (sqlite) — seeds audit rows via the existing recorder/model and asserts filtering, pagination, tenant isolation and RBAC.
