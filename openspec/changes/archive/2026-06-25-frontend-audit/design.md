## Context

The backend `/audit` module is a read-only, tenant-isolated query over the cross-cutting audit log
(recording lives in `shared/audit`; there are no write endpoints). Contract:

- `GET /audit/logs` — optional filters `action` (exact or dotted prefix, e.g. `login` matches
  `login.success`/`login.failure`), `actor_id`, `entity_type`, `entity_id`, `branch_id`; pagination
  `limit` (default 50) / `offset` (default 0). Returns a **plain list** ordered `created_at DESC` —
  **no `total`, no cursor**. `GET /audit/logs/{id}` — one entry. Perm `audit.read`.
- `AuditLog = { id, action, actor_id?, branch_id?, entity_type?, entity_id?, ip?, detail?,
  created_at? }`. `action`/`entity_type` are free strings (only `login.success`/`login.failure`
  emitted today, entity_type `user`); `detail` is a free-form ≤512-char string (no JSON diff field).

Two facts drive the design: (1) **actor names aren't in the log** — only `actor_id`, and the only
name source (`GET /rbac/users`) requires `rbac.manage`, which is *stricter* than `audit.read`; so
actor names are **best-effort** (resolved only when the viewer also has `rbac.manage`), degrading to
a short id; and (2) pagination is **offset-based with no total**, so the UI is "load more" and infers
end-of-list from a short page. There is **no date filter** server-side. The screen is purely
read-only. Conventions follow the existing screens (Vue 3 `<script setup>`, Pinia options store,
PrimeVue + Tailwind, the shared `@/lib/http` axios instance, mobile-first master–detail).

## Goals / Non-Goals

**Goals:**
- A read-only, filterable, paginated audit viewer that answers "who did what, when, from where".
- Best-effort actor names without requiring a new permission or backend change; honest degradation.
- Mirror the established store discipline and master–detail UX; zero write affordances.

**Non-Goals:**
- Any mutation (append-only, system-authored log); emitting more audit events; retention/export;
  tamper-evidence; a server-side date-range filter (the endpoint has none).

## Decisions

**1. Read-only master–detail.** An entry list (master) newest-first with filters and a load-more
control, and an entry detail (read-only) showing every field. On `< lg` the list drills into the
detail. No create/edit/delete anywhere — the screen is a viewer.

**2. Offset pagination with a "reached-end" heuristic.** The store keeps `offset` and `pageSize`
(50); `query(filters)` resets offset and loads page one; `loadMore()` advances offset and appends.
Since the response carries no total, `reachedEnd` is set when a page returns `< pageSize` rows, and
the load-more control hides. Changing any filter re-queries from offset 0. Rejected: faking a total
or a numbered pager — the API can't support either honestly.

**3. Actor names are best-effort, gated by `rbac.manage`.** On open, if `auth.can('rbac.manage')`,
the store loads `/rbac/users` (the same `rbac.api.listUsers` the staff screen uses) into an
`actorIndex` (id → name); otherwise it skips it. `actorName(actorId)` returns the name when known,
`"sistema"` when `actor_id` is null (system-authored), else `#<id slice>`. This keeps the change
frontend-only and never blocks the viewer for users without `rbac.manage` — they just see ids. The
cleaner fix (embed the actor name in the audit response, or a read-only `/users` endpoint) is a noted
backend follow-up, mirroring the customers person-embed but deliberately deferred.

**4. Filters: action / entity_type / actor / branch.** `action` is a free-text input (prefix-aware
per the backend), `entity_type` a free-text input, `actor` a select populated from the actor
directory when available (else hidden), and an optional "solo sucursal activa" toggle that sends the
active branch's id as `branch_id`. `entity_id` is not surfaced as a filter input this slice (it's
mostly reached by drilling from a row); the service still supports it.

**5. Labels and formatting.** `action`/`entity_type` render as-is (already human-ish dotted strings);
`created_at` formats via `toLocaleString('es-CO')`; `ip` and `detail` show in the detail pane. No
money/quantity formatting is involved.

**6. Store shape.** State: `entries: AuditLog[]`, `filters` (`{ action?, entityType?, actorId?,
branchId? }`), `offset`, `pageSize`, `reachedEnd`, `selectedId`, `actorIndex`, `loading`. Getters:
`selectedEntry`, `actorName(id)`. Actions: `loadActorDirectory()` (best-effort), `query(filters)`,
`loadMore()`, `select(id)`.

**7. Permission model.** Route guard `meta.permission: 'audit.read'`; nav link gated by `audit.read`.
No other permission gates content (the screen has no mutations). `rbac.manage` only enriches actor
names.

## Risks / Trade-offs

- **Actor shows as id without `rbac.manage`** → a pure auditor (audit.read only) sees `#id` actors. →
  Mitigation: degrade clearly (`#slice`, `sistema` for null); document the backend follow-up to embed
  the name. Many auditors are admins who have `rbac.manage` anyway.
- **No total / no exact end** → load-more relies on a short page to detect the end; a full final page
  shows one extra empty "load more" that then returns nothing and sets `reachedEnd`. → Acceptable and
  standard for total-less offset APIs.
- **No date filter** → can't jump to a date range server-side; the list is newest-first and
  paginated. → Out of scope; flagged for a backend filter later.
- **Sparse data today** → only login events are emitted, so the viewer will look thin until more
  write paths are instrumented (explicitly out of this capability's scope). → Expected; the viewer is
  ready for when more events land.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind the existing
`audit.read` permission. Rollback = revert the new files, the router entry, and the nav link; no
persisted client state.

## Open Questions

- Should the backend embed the actor's name in the audit response (or add a read-only `/users`
  endpoint) so actor names don't depend on `rbac.manage`? Recommended follow-up; deferred to keep this
  change frontend-only.
- Should a server-side date-range filter be added to `GET /audit/logs`? Deferred — useful once the
  log volume grows; needs a backend change.
