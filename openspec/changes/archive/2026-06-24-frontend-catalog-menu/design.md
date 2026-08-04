## Context

The frontend foundation (`src/lib/http.ts`, `src/lib/tokens.ts`, `src/stores/auth.ts`,
`src/router/index.ts`) and the RBAC screen are in place. Established patterns to mirror:

- **API clients** live in `src/services/<module>.api.ts` (e.g. `src/services/rbac.api.ts`): thin
  typed functions over the shared `http` Axios instance, exporting both functions and DTO types.
- **Stores** are Pinia options-API (`defineStore` with `state`/`getters`/`actions`). The RBAC store
  does per-write mutations followed by a refetch of the affected list — no optimistic cache.
- **Screens** follow `RbacView.vue`: a page shell (header with station label + logout) plus a sticky
  segmented "tab" control that swaps in panel components. Each panel implements the mobile-first
  master–detail per CLAUDE.md: one `selected` ref + `max-lg:hidden` classes, no router sub-routes.
- **Permission gating**: routes carry `meta.permission`; within screens, `auth.can('<code>')` decides
  whether mutation controls render. The backend enforces independently.
- **Station labels** (`src/lib/stations.ts`) already map `menu → Carta`, plus there is no `catalog`
  entry yet (falls back to title-case "Catalog").

Two gaps this change must confront: there is **no branch concept in the frontend yet** (a `grep
branch src/` returns nothing), and there is **no app navigation shell** — only `/rbac` exists and `/`
redirects to it.

## Goals / Non-Goals

**Goals:**
- Ship Menu (categories, products, addons, per-branch prices) and Catalog (units of measure) screens
  wired to the existing `/menu/*` and `/catalog/*` endpoints, gated by `menu.*` / `catalog.*`.
- Reuse the RbacView shell + master–detail pattern verbatim so the component vocabulary converges.
- Introduce the **minimum** branch-context primitive needed for per-branch prices, designed to extend
  to all branch-scoped modules later.
- Add a minimal navigation affordance so authenticated users can reach the new screens.

**Non-Goals:**
- Countries/cities catalog (address reference data; deferred until branch management lands).
- `product_variants` / `product_variant_options` SKU combinations (no backend endpoints yet).
- A full navigation/app-shell redesign or multi-branch switcher UX — only the minimum to function.
- Optimistic caching or offline support.

## Decisions

1. **File layout mirrors RBAC.** New files: `src/services/menu.api.ts`, `src/services/catalog.api.ts`;
   `src/stores/menu.ts`, `src/stores/catalog.ts`; `src/views/MenuView.vue`, `src/views/CatalogView.vue`;
   `src/components/menu/*` (e.g. `CategoriesPanel.vue`, `ProductsPanel.vue`, `AddonsPanel.vue`,
   `ProductDetail.vue`), `src/components/catalog/UnitsPanel.vue`.

2. **MenuView is tabbed like RbacView.** Segmented tabs: *Categorías · Productos · Adiciones*.
   Products is the richest panel: master list (filter by category + show-inactive) → detail with
   name/description/image, the per-branch price field, and an addon attach/detach sub-section.
   CatalogView starts single-panel (*Unidades*); tabs can be added if countries/cities arrive.

3. **Mutations follow the RBAC store discipline:** call the API, then refetch the affected list (no
   hand-maintained cache). Delete actions catch backend `409` and surface a non-destructive conflict
   message rather than removing the row.

4. **Branch context — minimal but real.** Add `src/stores/branch.ts` holding `branches` and an
   `activeBranchId`, resolved once via `ensureLoaded()`. **Resolved (confirmed against backend):** no
   module exposes a branch-listing endpoint — `BranchModel` exists but is reachable only through the
   seed. So `ensureLoaded()` reads `import.meta.env.VITE_DEFAULT_BRANCH_ID` (a config seam mirroring
   the existing `VITE_API_BASE_URL`): if set, that is the active branch and prices work today; if
   unset, `activeBranchId` stays null and per-branch price editing shows a "selecciona sucursal" empty
   state. `ensureLoaded()` localizes the seam so swapping in a real `GET /branches` later touches one
   function. This keeps prices honest without blocking the rest of the Menu screen.

5. **Navigation: a thin guarded nav.** Add a small nav (links to the modules the user can read:
   Accesos, Carta, Catálogo) in a shared layout or the existing screens' headers. Each link is shown
   only when `auth.can('<module>.read')`. Keep it minimal; a real app shell is a later change. Per the
   CLAUDE.md PrimeIcons note, put responsive `hidden` classes on a wrapping `<span>`, never on `.pi`.

6. **Types come from the backend contract**, not invented: Product (`id`, `category_id`, `name`,
   `description?`, `image_url?`, `is_active`), Category (`id`, `name`, `parent_id?`, `is_active`),
   Addon (`id`, `name`, `price`, `is_active`), ProductPrice (`product_id`, `branch_id`, `price`,
   `is_active`), Unit (base vs derived with `base_unit_id` + conversion factor). Money is a decimal
   **string** from the API — keep it a string in transit, format only for display.

## Risks / Trade-offs

- **Branch source is unresolved.** `/auth/me` does not return branches and no branches endpoint is
  confirmed in the frontend. Mitigation: implement `branch.ts` against the documented branch endpoint
  if one exists; if not, gate price editing behind branch availability (decision 4) and split price
  management into its own task that can land once branch resolution is settled. This is the main risk
  and is deliberately decoupled so Menu CRUD ships regardless.
- **No nav shell exists**, so this change introduces navigation scope creep risk. Mitigation: keep the
  nav to a permission-filtered link list; defer any real layout/shell to a dedicated change.
- **409-on-delete UX**: backend blocks deletes with dependents. Trade-off: we surface a friendly
  conflict and steer users toward `is_active = false` (soft retire) as the normal path.
- **Decimal money as string**: avoids float rounding bugs but requires careful input parsing/validation
  in the price/addon forms.
