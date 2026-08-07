## Why

Every operational and back-office module (orders, inventory, cash, kitchen, delivery, purchasing, finance, staff) is **branch-scoped** — its endpoints take a `branch_id` in the path. But the frontend has no real branch context: `stores/branch.ts` is a stub that reads a single id from the `VITE_DEFAULT_BRANCH_ID` build-time env var, because the backend exposes **no endpoint to list a tenant's branches**. There is also no UI to see or switch the active branch. This blocks building any further frontend module, since each new screen would hard-depend on a hand-configured env var and could never support a multi-branch tenant.

## What Changes

- **Backend**: add a read-only, tenant-scoped `GET /branches` endpoint that returns the active branches of the current tenant (resolved by the existing subdomain middleware). Authenticated access only — listing your own branches is a session primitive, not a gated permission.
- **Frontend — branch context store**: replace the env-var stub with a real async `ensureLoaded()` that fetches branches from `GET /branches`, selects a sensible default (the primary branch, else the first), and persists the user's choice in `localStorage` so it survives reloads. Add `setActiveBranch(id)`.
- **Frontend — branch selector UI**: a selector mounted in the app shell (sidebar footer on lg+, mobile top bar below lg) showing the active branch and allowing a switch when the tenant has more than one. Single-branch tenants render a static label.
- **Frontend — adopt the async seam**: update the current consumers (`menu/ProductsPanel.vue`, `menu/ProductDetail.vue`) that call the previously-synchronous `ensureLoaded()` so prices load against the resolved branch. Remove the `VITE_DEFAULT_BRANCH_ID`-only copy ("configura una sucursal…") in favor of real state.
- **BREAKING** (internal only): `useBranchStore().ensureLoaded()` becomes async and network-backed; callers must `await` it. No public API surface affected.

## Capabilities

### New Capabilities
- `branch-directory`: backend endpoint to list the current tenant's branches (id, code, name, is_primary), read-only and authenticated, so clients can discover branches instead of hard-coding ids.
- `frontend-branch-context`: a shared client-side active-branch context (load, default, persist, switch) plus a branch selector in the app shell, consumed by every branch-scoped screen.

### Modified Capabilities
<!-- None: existing specs' requirements are unchanged. The menu screens are touched at the implementation level only (awaiting an async store), not at the spec/requirement level. -->

## Impact

- **Backend**: new router for `GET /branches` (tenant-scoped, co-located with `shared/tenancy`); `BranchModel` already exists in `shared/tenancy/models.py`. Adds an integration test. No migration (table exists).
- **Frontend**: new `services/branch.api.ts`; rewritten `stores/branch.ts` (+ unit tests); new branch-selector component wired into `AppShell.vue` / `AppSidebar.vue`; edits to `menu/ProductsPanel.vue` and `menu/ProductDetail.vue` for the async load.
- **Config**: `VITE_DEFAULT_BRANCH_ID` is retired as the source of truth (kept, if at all, only as an offline/dev fallback).
- **Unblocks**: all subsequent branch-scoped frontend modules (orders, inventory, cash, …) gain a ready-to-read `activeBranchId`.
