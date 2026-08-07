## 1. Service layer

- [x] 1.1 Create `front/src/services/audit.api.ts` with type `AuditLog` (`id, action, actor_id?, branch_id?, entity_type?, entity_id?, ip?, detail?, created_at?`)
- [x] 1.2 Add `listLogs(filters)` (`GET /audit/logs` with optional `action`/`actor_id`/`entity_type`/`entity_id`/`branch_id` + `limit`/`offset`, omitting unset params) and `getLog(id)` (`GET /audit/logs/{id}`)
- [x] 1.3 Add service unit tests in `front/src/services/__tests__/audit.api.spec.ts` (omitted-vs-set params, limit/offset, single-get path, returned shape)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/audit.ts` (Pinia options) state: `entries`, `filters`, `offset`, `pageSize` (50), `reachedEnd`, `selectedId`, `actorIndex`
- [x] 2.2 Add `query(filters)` (reset offset, load first page) and `loadMore()` (advance offset, append); set `reachedEnd` when a page returns fewer than `pageSize`
- [x] 2.3 Add `loadActorDirectory()` — best-effort: only when `auth.can('rbac.manage')`, load `/rbac/users` into `actorIndex`; add `actorName(id)` getter (`sistema` for null, `#slice` fallback) and `selectedEntry` getter
- [x] 2.4 Add `select(id)` and a `select`-loads-detail path (use the loaded entry; fetch by id only if not present)
- [x] 2.5 Add store unit tests: query loads page + offset reset, load-more appends, reached-end on short page, actor-name resolution + fallback (with and without directory)

## 3. Screen, components, routing

- [x] 3.1 Add `/audit` route (name `audit`, `meta.permission: 'audit.read'`) in `front/src/router/index.ts` and a nav link (`Auditoría`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/AuditView.vue` container + `AuditPanel.vue` orchestrator: load actor directory (best-effort) + first page, filter bar (action, entity type, actor-when-available, solo-sucursal-activa), error/empty states
- [x] 3.3 Create the entry list (master): rows showing action, actor name, entity (type + short id), timestamp (newest-first); drill-down on `< lg`; a "Cargar más" control hidden when `reachedEnd`
- [x] 3.4 Create `AuditDetail.vue`: read-only detail of all fields — action, actor (name/id), entity type + id, branch, IP, detail text, timestamp; no mutation controls
- [x] 3.5 Format timestamps (`es-CO`); resolve actor names from the store; surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: trigger an event (e.g. a failed + successful login) → open the screen → see entries newest-first → filter by `action=login` → open an entry detail (IP, detail, timestamp) → load more / reached-end behaves; verify a user without `audit.read` is redirected, and actor shows a name with `rbac.manage` / an id without it
