## Why

The backend `/purchasing` module exposes the supply side of inventory — suppliers, their ingredient
catalog, purchase requests, orders, goods receipt, and payments — but has no frontend. The
foundation everything else depends on is **supplier master data**: a restaurant can't raise a
purchase request or order without suppliers and a record of which ingredients each one sells (and at
what reference price). This change builds that foundation first, so the procure-to-pay flow
(requests → orders → receipt → payments) can land as a follow-up against real suppliers rather than
stub data.

## What Changes

- Add a **Purchasing service layer** (`purchasing.api.ts`) over the supplier slice of `/purchasing`:
  list suppliers (`GET /purchasing/suppliers`, optional `active` filter), create
  (`POST /purchasing/suppliers`), update/deactivate (`PATCH /purchasing/suppliers/{id}` — the same
  endpoint sets contact fields and flips `is_active`), list a supplier's ingredients
  (`GET /purchasing/suppliers/{id}/ingredients`), attach one
  (`POST /purchasing/suppliers/{id}/ingredients`), and detach one
  (`DELETE /purchasing/suppliers/{id}/ingredients/{ingredientId}`).
- Add a **Purchasing store** (`purchasing.ts`): the tenant's suppliers, the selected supplier's
  ingredient catalog, and an ingredient directory (id → name + unit) resolved from
  `/recipes/ingredients` crossed with the catalog units, so the catalog shows names not UUIDs.
  Reference prices are carried as string-decimals.
- Add the **PurchasingView** screen, mobile-first master–detail (the house pattern):
  - **Suppliers list** (master): name + active badge, with an "solo activos" filter. Read needs
    `purchasing.read`.
  - **Supplier detail**: contact info (tax id, phone, email, address) with an edit form and a
    deactivate action, plus the supplier's **ingredient catalog** — each row showing ingredient
    name, unit, and reference price, with **attach** (pick ingredient + unit + reference price) and
    **detach** controls. All mutations gated by `purchasing.manage`.
- Add the **route + nav entry** (`/purchasing`, permission `purchasing.read`) and a navigation link.
- Unit tests for the service and store (URLs/payloads, the active filter, write-through refetch,
  ingredient-label resolution, and the duplicate-attach conflict).

Non-goals (deferred to a follow-up `frontend-purchasing-orders` change): purchase requests and their
approval, purchase orders from approved requests, goods receipt into inventory, and supplier
payments. Also out of scope: ingredient CRUD (owned by the recipes module — this screen only reads
the directory), supplier-side analytics/price history, and realtime/auto-refresh (manual refresh
this slice). Suppliers are tenant-wide, so there is no branch scoping on this screen.

## Capabilities

### New Capabilities
- `frontend-purchasing`: the supplier master-data frontend — list/create/edit/deactivate suppliers
  (tenant-scoped) and manage each supplier's ingredient catalog (attach/detach with a unit and
  reference price), with ingredient names/units resolved from the recipes and catalog modules and
  all mutations gated by `purchasing.read` / `purchasing.manage`.

### Modified Capabilities
<!-- None. Consumes the existing purchasing-management backend unchanged (supplier slice only);
     ingredient/unit data is read-only from recipes-management and catalog-management. -->

## Impact

- **Frontend code**: new `front/src/services/purchasing.api.ts`, `front/src/stores/purchasing.ts`,
  `front/src/views/PurchasingView.vue`, and `front/src/components/purchasing/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the existing `recipes.api.ts` ingredient read (added in `frontend-inventory`), the
  catalog store (units → name/abbreviation), the shared `http` axios instance, `@/lib/money`
  `formatCOP`, and the `apiError` helpers. No active-branch context (suppliers are tenant-scoped).
- **Backend**: none — consumes existing `/purchasing` supplier endpoints plus `/recipes/ingredients`
  and `/catalog/units`.
- **Permissions/RBAC**: relies on `purchasing.read` (screen + read) and `purchasing.manage`
  (supplier create/edit/deactivate, catalog attach/detach); label data additionally reads
  `recipes.read` / `catalog.read` and degrades gracefully. No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
