## Why

The backend `/audit` module exposes a read-only, tenant-isolated audit trail ("who did what, when,
from where") but has no frontend, so the log is unreachable from the UI. It's the last cross-cutting
module without a screen; a simple viewer lets an admin/auditor answer accountability and debugging
questions (e.g. failed logins, who changed what) without database access.

## What Changes

- Add an **Audit service layer** (`audit.api.ts`) over `/audit`: list entries
  (`GET /audit/logs` with optional `action`, `actor_id`, `entity_type`, `entity_id`, `branch_id`
  filters and `limit`/`offset` pagination) and get one (`GET /audit/logs/{id}`).
- Add an **Audit store** (`audit.ts`): the loaded entries (newest-first), the active filters, and
  offset-based pagination (the endpoint returns a plain list with no total, so the store tracks
  whether the last page was full to know if more may exist). Plus a **best-effort actor directory**
  — when the current user also holds `rbac.manage`, the store loads `/rbac/users` to resolve
  `actor_id` → name; otherwise actor shows as a short id reference.
- Add the **AuditView** screen, mobile-first master–detail (read-only):
  - **Entry list** (master): each row showing the action, actor, entity (type + short id), and
    timestamp, newest-first; filters for action (exact or dotted prefix like `login`), entity type,
    and actor (when the directory is available), plus a "solo sucursal activa" branch filter; and a
    "cargar más" pagination control.
  - **Entry detail**: all fields — action, actor (name/id), entity type + id, branch, IP, the
    free-form `detail` text, and the timestamp.
- Add the **route + nav entry** (`/audit`, permission `audit.read`) and a navigation link.
- Unit tests for the service and store (URLs/params, the prefix filter, offset pagination + the
  reached-end signal, and actor-name resolution with graceful fallback).

Non-goals: any write/mutation (the log is append-only and system-authored — there are no write
endpoints); instrumenting more backend write paths to emit events; retention/archival/export;
tamper-evidence (signing/hash-chaining); and a server-side date-range filter (the endpoint exposes no
date filter — the list is newest-first and paginated). A read-only `/users` endpoint or an embedded
actor name in the audit response (to drop the `rbac.manage` dependency for names) is noted as a
possible backend follow-up, not built here.

## Capabilities

### New Capabilities
- `frontend-audit`: the audit-log viewer — a read-only, filterable, paginated view of the tenant's
  audit trail (action, actor, entity, branch, IP, detail, timestamp), gated by `audit.read`, with
  best-effort actor-name resolution when the user also has `rbac.manage`.

### Modified Capabilities
<!-- None. Consumes the existing audit-query backend unchanged; actor names are read-only and
     best-effort from rbac-management. -->

## Impact

- **Frontend code**: new `front/src/services/audit.api.ts`, `front/src/stores/audit.ts`,
  `front/src/views/AuditView.vue`, and `front/src/components/audit/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the existing `rbac.api` `listUsers` (best-effort actor directory), the active-branch
  context (optional branch filter), the shared `http` axios instance, and the `apiError` helpers.
- **Backend**: none — consumes existing `/audit` read endpoints.
- **Permissions/RBAC**: relies on `audit.read` (screen + read); actor-name resolution additionally
  uses `rbac.manage` and degrades to id references without it. No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
