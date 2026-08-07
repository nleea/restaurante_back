## Context

The backend is branch-multitenant: `BranchScopedMixin` anchors every business entity to `branches.id`, and operational routers expose `/branches/{branch_id}/...` paths (inventory, cash, orders, …). Branches live in `shared/tenancy/models.py` (`BranchModel`: `id`, `tenant_id`, `code`, `name`, `city_id?`, `is_primary`, `is_active`) and the tenant is resolved per request by the subdomain middleware (`shared/api/deps.py: get_tenant_id`).

On the frontend, `stores/branch.ts` is a placeholder that reads `VITE_DEFAULT_BRANCH_ID` and fabricates a single `{ id, name: 'Sucursal principal' }`. Only `menu/ProductsPanel.vue` and `menu/ProductDetail.vue` consume it (for per-branch prices), calling `ensureLoaded()` synchronously in `onMounted`. There is no branch selector anywhere, and no API to discover branches — so no further branch-scoped screen can be built honestly. This change closes that gap with the smallest backend addition (a read endpoint) plus a real frontend context + selector.

## Goals / Non-Goals

**Goals:**
- A tenant-scoped `GET /branches` read endpoint so clients discover branches instead of hard-coding ids.
- A real frontend branch context: load from API, sensible default, persisted user choice, switch action.
- A branch selector in the app shell (desktop sidebar + mobile top bar).
- Keep existing menu price flows working against the resolved active branch.

**Non-Goals:**
- Branch CRUD (create/edit/deactivate branches) — out of scope; the seed still owns branch creation.
- Per-branch data isolation in other modules' UIs (those arrive with each module's own change).
- Changing how the backend resolves tenant (subdomain middleware stays as-is).
- A backend permission gate for listing branches (intentionally authenticated-only).

## Decisions

### 1. `GET /branches` is authenticated-only, tenant-scoped, read-only
Listing the branches you can work in is a session primitive, like `/auth/me`. Gating it behind an RBAC code would create a chicken-and-egg problem (you need a branch to act, but couldn't see branches without a permission). It returns only `is_active` branches of the request's tenant. **Alternative considered:** a `branches.read` permission — rejected as friction with no security benefit, since the data is already tenant-isolated and non-sensitive.

### 2. Endpoint placement: a thin router co-located with `shared/tenancy`
`BranchModel` already lives in `shared/tenancy`. Rather than invent a full hexagonal "branches" module (entities/ports/use-cases) for a single read, add a minimal tenant-scoped router that queries `BranchModel` filtered by `tenant_id`, mirroring how `catalog` exposes simple reads. **Alternative considered:** a full module — rejected as over-engineering for one read-only list. If branch CRUD lands later, it can graduate into a module then.

### 3. `ensureLoaded()` becomes async and network-backed
The store fetches once and caches (`loaded` flag). Consumers must `await ensureLoaded()` before reading `activeBranchId`. Only two call sites exist today (the menu panels); both already `await` in `onMounted`-style flows, so the change is localized. **Alternative considered:** keep a sync API and prefetch globally at bootstrap — rejected because it couples branch loading to auth bootstrap and hides failures; an explicit awaited load per screen is clearer.

### 4. Selection priority: persisted → primary → first
On load: if a `localStorage` id still matches a returned branch, restore it; else pick `is_primary`; else the first. This makes single-branch tenants "just work" and respects an explicit user choice across reloads. Persist on every `setActiveBranch`.

### 5. Selector lives in the shell, not per-screen
Mount it in `AppSidebar.vue` (footer, lg+) and `AppShell.vue` mobile top bar so the active branch is always visible and global. Single-branch tenants render a static label (no dropdown) to avoid implying a choice that doesn't exist.

### 6. Retire `VITE_DEFAULT_BRANCH_ID` as source of truth
Real API state replaces it. Keep it, if at all, only as an optional offline/dev fallback inside the store; remove the menu UI copy that instructs configuring it.

## Risks / Trade-offs

- **Async seam breaks menu callers** → both consumers are updated in this change; unit tests cover the store and the menu price flow continues to read `activeBranchId` after `await ensureLoaded()`.
- **Empty/again-empty branch list** → `hasActiveBranch=false` path is specified and rendered (screens that need a branch show a neutral empty state instead of erroring).
- **Stale persisted id after a branch is deactivated** → load-time validation discards ids not present in the response and falls back to the default.
- **Endpoint leaks cross-tenant branches** → query filters strictly by `get_tenant_id(request)`; an integration test asserts tenant isolation.
- **Over-minimal backend now, CRUD later** → accepted; the read router is a stepping stone and can be absorbed into a future branches module without breaking the frontend contract (same response shape).

## Migration Plan

1. Backend: add `GET /branches` router + response schema, register in `main.py`, add integration test (auth required, tenant isolation, excludes inactive). No DB migration (table exists).
2. Frontend: add `services/branch.api.ts`; rewrite `stores/branch.ts` (async load, default, persist, `setActiveBranch`) with unit tests.
3. Frontend: build the branch-selector component; wire into `AppSidebar.vue` and `AppShell.vue`.
4. Frontend: update `menu/ProductsPanel.vue` and `menu/ProductDetail.vue` to `await ensureLoaded()` and drop the `VITE_DEFAULT_BRANCH_ID` copy.
5. Validate: `ruff`/`mypy`/`pytest` (backend) and type-check/lint/unit/build (frontend).

Rollback: revert the frontend store to the env-var stub; the backend endpoint is additive and can stay.

## Open Questions

- Should the selector also surface branch `code` (e.g., "Centro · C-01") for tenants with similarly named branches, or just `name`? Default: `name` only, revisit if needed.
- Do we want the active branch echoed into request headers for observability, or is the path `branch_id` enough? Default: path only for now.
