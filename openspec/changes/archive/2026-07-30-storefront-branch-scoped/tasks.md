## 1. Backend — branch resolution

- [x] 1.1 Add `get_branch_id_by_code(tenant_id, code) -> uuid | None` to the storefront
      repository port + SQLAlchemy implementation, filtered to `is_active = true`
- [x] 1.2 Add `list_active_branches(tenant_id) -> list[StoreBranch]` (code, name, address)
      to the port + implementation; add the `StoreBranch` domain entity
- [x] 1.3 Add `BranchNotFoundError` to `shared/domain/errors.py` and map it to HTTP 404 in
      `shared/api/errors.py`

## 2. Backend — branch-scoped service

- [x] 2.1 `StorefrontService.get_menu(tenant_id, branch_id)` — take the branch as an
      argument instead of calling `get_primary_branch_id` (`manage_storefront.py:86`)
- [x] 2.2 `StorefrontService.create_order(tenant_id, branch_id, command)` — same, replacing
      the resolver at `manage_storefront.py:101`
- [x] 2.3 Add `resolve_branch(tenant_id, code | None) -> uuid` on the service: `None` →
      primary branch; a code → `get_branch_id_by_code` or raise `BranchNotFoundError`
- [x] 2.4 Add `list_branches(tenant_id)` on the service
- [x] 2.5 Confirm `StorefrontOrderCommand` gains no branch field — the branch stays a
      resolver argument so the body cannot select it

## 3. Backend — routes

- [x] 3.1 Add `GET /storefront/{branch_code}/menu` and
      `POST /storefront/{branch_code}/orders`; both resolve via `resolve_branch`
- [x] 3.2 Keep `GET /storefront/menu` and `POST /storefront/orders`, delegating to the same
      handlers with `code = None`
- [x] 3.3 Add `GET /storefront/branches`
- [x] 3.4 Verify the caja-closed rejection now evaluates the **addressed** branch's session

## 4. Backend — branch code format

- [x] 4.1 Add a slug validator (`^[a-z0-9]+(-[a-z0-9]+)*$`, max 32) on the branch write
      path; reject with 422
- [x] 4.2 Update dev seeds so every seeded branch has a slug-safe `code`
- [x] 4.3 Confirm the existing `UniqueConstraint(tenant_id, code)` still carries uniqueness
      (no new DB constraint)

## 5. Backend — tests

- [x] 5.1 `GET /storefront/{code}/menu` returns the addressed branch's prices; two branches
      of one tenant return different menus
- [x] 5.2 Hours/next-opening in the menu response belong to the addressed branch
- [x] 5.3 Unknown code → 404; inactive branch code → 404; no order created on any branch
- [x] 5.4 `POST /storefront/{code}/orders` creates the order on that branch (order, items,
      delivery all carry it)
- [x] 5.5 Caja closed on the addressed branch → 409 even when another branch is open
- [x] 5.6 Code-less endpoints still resolve the primary branch (regression)
- [x] 5.7 `GET /storefront/branches` lists active only
- [x] 5.8 Branch write rejects non-slug codes, accepts `centro-norte`

## 6. Frontend — route and data

- [x] 6.1 `/store` → `/store/:branchCode?` in `src/router/index.ts:34`
- [x] 6.2 Storefront store reads the code from the route and calls the branch-scoped
      endpoints (falling back to the code-less ones when absent)
- [x] 6.3 `StorefrontView.vue` renders the addressed branch's menu, hours and open state
- [x] 6.4 Checkout submits to the branch-scoped intake

## 7. Frontend — picker and states

- [x] 7.1 Branch picker component fed by `GET /storefront/branches`; shown only when no code
      is in the route AND the tenant has more than one active branch
- [x] 7.2 Not-found state for an unresolvable code, offering the picker; never falls back to
      another branch's menu
- [x] 7.3 Clear the cart on branch change, with a visible notice; preserve it on reload of
      the same branch

## 8. Frontend — tests

- [x] 8.1 `/store/centro` loads that branch's menu; `/store` loads the primary branch
- [x] 8.2 Unknown code renders the not-found state, not a menu
- [x] 8.3 Picker appears only for multi-branch tenants
- [x] 8.4 Cart clears on branch change and survives a same-branch reload

## 9. Quality gates

- [x] 9.1 Backend: `ruff`, `mypy --strict`, full `pytest` green
- [x] 9.2 Frontend: lint, type-check, unit tests, production build green
