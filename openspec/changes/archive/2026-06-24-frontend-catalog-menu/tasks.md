## 1. API clients (typed services)

- [x] 1.1 Create `src/services/menu.api.ts`: DTO types (Category, Product, Addon, ProductPrice) and functions for categories CRUD (`/menu/categories`), products CRUD (`/menu/products`), addons CRUD (`/menu/addons`), product↔addon attach/detach, and price upsert (`PUT /menu/products/{id}/prices/{branch_id}`).
- [x] 1.2 Create `src/services/catalog.api.ts`: Unit DTO (base vs derived with `base_unit_id` + conversion factor) and units-of-measure CRUD over `/catalog/*`.
- [x] 1.3 Keep money fields as decimal strings in DTOs; do not coerce to number in transit.

## 2. Stores

- [x] 2.1 Create `src/stores/menu.ts` (Pinia options-API): state for categories/products/addons; actions that write then refetch the affected list; getters for products-by-category and active/inactive filtering.
- [x] 2.2 Create `src/stores/catalog.ts`: state for units; create/edit actions with write-then-refetch; getter splitting base vs derived units.
- [x] 2.3 Create `src/stores/branch.ts`: `branches` + `activeBranchId`, with `ensureLoaded()` isolating the branch source; expose `activeBranchId` for price editing.

## 3. Routing & navigation

- [x] 3.1 Add guarded routes in `src/router/index.ts`: `/menu` (`permission: 'menu.read'`) → `MenuView`, `/catalog` (`permission: 'catalog.read'`) → `CatalogView`.
- [x] 3.2 Add a `catalog → Catálogo` entry to `src/lib/stations.ts`.
- [x] 3.3 Add a minimal permission-filtered nav (links shown only when `auth.can('<module>.read')`) reachable from the authenticated screens; responsive `hidden` classes go on a wrapping `<span>`, never on `.pi`.

## 4. Catalog screen

- [x] 4.1 Build `src/views/CatalogView.vue` reusing the RbacView shell (header + station label + logout).
- [x] 4.2 Build `src/components/catalog/UnitsPanel.vue`: master–detail list of units (base vs derived shown distinctly) using one `selected` ref + `max-lg:hidden`.
- [x] 4.3 Add create/edit form for units; derived units require an existing base unit + factor; surface backend validation errors inline; hide mutation controls unless `auth.can('catalog.manage')`.

## 5. Menu screen — categories & products

- [x] 5.1 Build `src/views/MenuView.vue` with segmented tabs (Categorías · Productos · Adiciones), mirroring RbacView.
- [x] 5.2 Build `src/components/menu/CategoriesPanel.vue`: master–detail CRUD with optional `parent_id`; delete catches `409` and shows a conflict message; mutation controls gated by `menu.manage`.
- [x] 5.3 Build `src/components/menu/ProductsPanel.vue`: master list with category filter + show-inactive toggle; detail (`ProductDetail.vue`) edits name/description/image and retires via `is_active`; delete catches `409`.

## 6. Menu screen — prices & addons

- [x] 6.1 In `ProductDetail.vue`, add the per-branch price field bound to `branch.activeBranchId`; on save `PUT` to `/menu/products/{id}/prices/{branchId}`; when no active branch, show a "selecciona sucursal" empty state instead of the field.
- [x] 6.2 Build `src/components/menu/AddonsPanel.vue`: CRUD over `/menu/addons` (price as decimal string).
- [x] 6.3 In `ProductDetail.vue`, add an addon attach/detach sub-section calling the product↔addon endpoints and reflecting the product's available addons.

## 7. Verification

- [x] 7.1 Add unit tests (Vitest) for the menu and catalog stores (write-then-refetch, filtering getters) mirroring `src/stores/__tests__`.
- [ ] 7.2 Manually verify against the seeded `demo` tenant (`admin@demo.com`): categories/products/addons CRUD, price upsert, units CRUD, and that `menu.read`/`catalog.read`-only users see no mutation controls and are redirected from guarded routes when lacking read.
- [x] 7.3 Run `pnpm type-check`, `pnpm lint`, and `pnpm test:unit`; confirm all pass.
