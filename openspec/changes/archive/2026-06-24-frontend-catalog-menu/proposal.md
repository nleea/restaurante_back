## Why

The frontend has its foundation (HTTP client, auth, RBAC routing) and the RBAC screen in place,
but **no business-module screens exist yet**. Catalog and Menu are the foundational reference-data
modules: Orders, Inventory, and Recipes all depend on products, categories, units of measure, and
prices existing first. The backend `/menu` and `/catalog` APIs are already built, so this change
delivers the first vertical slice of real product value and consolidates the component vocabulary
(reusing the `RbacView` master–detail pattern) before tackling the more complex operational core.

## What Changes

- New **Menu** management screens wired to `/menu/*`:
  - **Categories** — CRUD with optional hierarchy (`parent_id`), `active` filter; delete guarded by
    backend `409` when dependents exist (surface as a friendly conflict message).
  - **Products** — CRUD with filters (`category_id`, `active`), optional `description`/`image_url`,
    soft-retire via `is_active`.
  - **Per-branch prices** — manage `product_prices` through `PUT /menu/products/{id}/prices/{branch_id}`
    (branch-scoped upsert), scoped by the active branch.
  - **Addons** — CRUD over `/menu/addons` plus attach/detach to a product
    (`/menu/products/{id}/addons/{addon_id}`).
- New **Catalog** management screen wired to `/catalog/*`:
  - **Units of measure** — CRUD for base and derived units (derived carry a `base_unit_id` +
    conversion factor); this is the catalog slice Inventory/Recipes need.
- New routes (`/menu`, `/catalog`) guarded by `meta.permission` and a navigation shell to reach them.
- Pinia stores + typed API clients for menu and catalog entities, all through the single Axios instance.

Non-goals (deferred): countries/cities catalog (address data, needed when branch management lands);
`product_variants` / `product_variant_options` (no backend endpoints yet — reserved for Recipes/Orders).
Variant groups/options endpoints exist and MAY be included as a stretch within the product detail.

## Capabilities

### New Capabilities
- `frontend-menu`: Menu management UI — categories, products, per-branch prices, and addons —
  gated by `menu.read` / `menu.manage`, following the mobile-first master–detail pattern.
- `frontend-catalog`: Catalog management UI — units of measure (base/derived) — gated by
  `catalog.read` / `catalog.manage`.

### Modified Capabilities
<!-- None: this change adds frontend capabilities; backend specs (menu, catalog) are unchanged. -->

## Impact

- **New code**: `src/views/MenuView.vue`, `src/views/CatalogView.vue`, `src/components/menu/*`,
  `src/components/catalog/*`, `src/stores/menu.ts`, `src/stores/catalog.ts`, typed API modules under
  `src/lib/` (or `src/api/`).
- **Modified code**: `src/router/index.ts` (new guarded routes), app navigation shell, possibly
  `src/lib/stations.ts` if module→station labels are extended.
- **Dependencies**: none new — reuses Axios instance, PrimeVue, Tailwind tokens, branch scoping.
- **Backend**: consumes existing `/menu/*` and `/catalog/*` endpoints; no backend changes.
