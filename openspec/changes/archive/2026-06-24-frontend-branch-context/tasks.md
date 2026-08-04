## 1. Backend — `GET /branches` endpoint

- [x] 1.1 Add a `BranchResponse` schema (`id`, `code`, `name`, `is_primary`) for the tenancy/branches read.
- [x] 1.2 Add a tenant-scoped router exposing `GET /branches` that queries `BranchModel` filtered by tenant (auto tenancy filter) and `is_active = true`, ordered with the primary branch first; authenticated session required, no RBAC permission code. (Placed in the identity module, not `shared/tenancy`, because `shared` must not import `modules` for `get_current_user`.)
- [x] 1.3 Register the new router in `main.py`.
- [x] 1.4 Add an integration test: returns the tenant's active branches; excludes inactive; enforces tenant isolation (no cross-tenant leak); `401` when unauthenticated.
- [x] 1.5 Run `ruff`, `mypy`, and `pytest` green.

## 2. Frontend — branch service & store

- [x] 2.1 Add `services/branch.api.ts` with `listBranches()` returning `{ id, code, name, is_primary }[]` from `GET /branches`.
- [x] 2.2 Rewrite `stores/branch.ts`: async `ensureLoaded()` that fetches once (idempotent via `loaded`), stores `branches` and `activeBranchId`, exposes `hasActiveBranch`.
- [x] 2.3 Implement default selection: persisted `localStorage` id (if still present) → `is_primary` → first; `null` when no branches.
- [x] 2.4 Implement `setActiveBranch(id)` that updates state and persists the choice to `localStorage`.
- [x] 2.5 Add unit tests: first-load fetch, idempotent reload, primary-preferred default, first-branch fallback, empty list, persisted-restore, stale-id discarded.

## 3. Frontend — branch selector in the shell

- [x] 3.1 Build a `BranchSelector` component showing the active branch name; dropdown to switch when `branches.length > 1`, static label when single, neutral state when none.
- [x] 3.2 Mount it in `AppSidebar.vue` (footer, lg+) and `AppShell.vue` mobile top bar, styled with the "El Pase" design system.
- [x] 3.3 Ensure the shell calls `branch.ensureLoaded()` (errors swallowed) so the selector hydrates after login/reload.

## 4. Frontend — adopt the async seam in menu

- [x] 4.1 Update `menu/ProductsPanel.vue` to `await branch.ensureLoaded()` before loading prices and read `activeBranchId` reactively.
- [x] 4.2 Update `menu/ProductDetail.vue` likewise; remove the `VITE_DEFAULT_BRANCH_ID` "configura una sucursal" copy in favor of real state (keep a neutral message only for the genuine no-branch case).
- [x] 4.3 Retire `VITE_DEFAULT_BRANCH_ID` as source of truth (removed store usage and the `env.d.ts` type declaration).

## 5. Validation

- [x] 5.1 Frontend: type-check, lint (oxlint + eslint), 30 unit tests, and production build all green. (Backend: ruff, mypy, 3 integration tests green.)
- [x] 5.2 Verified at the HTTP/ASGI level via the integration test (login → `GET /branches` through the real tenancy middleware: active-only, tenant-isolated, primary-first, 401 unauth) and selection logic via store unit tests; the real `scripts.seed` creates a primary "Main Branch", so a live boot shows the selector populated. Live browser session not run in this pass.
