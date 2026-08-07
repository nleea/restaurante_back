## Why

The backend `/inventory` module — branch-scoped stock with reorder thresholds and an auditable
in/out/adjustment movement ledger — has no frontend, so a manager can't see what's on hand, spot
what's below its reorder point, or record receipts, consumption, and physical counts from the UI.
Inventory is the back-office counterpart to orders/cash and the stock half of the recipes/BOM hinge;
without it the pilot restaurants fall back to spreadsheets for stock control.

## What Changes

- Add an **Inventory service layer** (`inventory.api.ts`) over `/inventory` (all paths
  branch-scoped): list stock (`GET /branches/{b}/stock`), low-stock view
  (`GET /branches/{b}/stock/low`), one ingredient's stock (`GET /branches/{b}/stock/{ing}`), set
  reorder threshold (`PUT /branches/{b}/stock/threshold`), register a movement
  (`POST /branches/{b}/movements`), physical recount (`POST /branches/{b}/recounts`), and movement
  history (`GET /branches/{b}/movements/{ing}`).
- Add a minimal **ingredients read service** (`recipes.api.ts` → `listIngredients`) over
  `/recipes/ingredients`, since stock rows carry only `ingredient_id` and the names/units live in
  the recipes + catalog modules.
- Add an **Inventory store** (`inventory.ts`): the active branch's stock rows, an ingredient
  directory (id → name + unit) resolved from `/recipes/ingredients` crossed with the existing
  catalog units, the selected ingredient's movement history, plus a `lowStock` view. Quantities are
  carried as string-decimals; the only client computation is the at-or-below-threshold flag.
- Add the **InventoryView** screen, mobile-first master–detail (the house pattern):
  - **Stock list** (master): one row per tracked ingredient — name, unit, on-hand, reorder point,
    and a low-stock badge — with a "solo bajo stock" filter. Read needs `inventory.read`.
  - **Ingredient detail**: on-hand vs reorder point; **set threshold**, **registrar movimiento**
    (in/out, quantity, reason, optional notes), and **recuento físico** (counted quantity → records
    the delta as an adjustment), each gated by `inventory.adjust` and attributed to an employee
    (reuse the staff picker); plus the ingredient's movement history newest-first.
- Add the **route + nav entry** (`/inventory`, permission `inventory.read`) and a navigation link.
- Unit tests for the services and store (URLs/payloads/branch-scoped paths, write-through refetch,
  ingredient-label resolution, and the low-stock flag).

Non-goals: ingredient CRUD (managed by the recipes module — this screen only reads the directory);
the orders→recipes→inventory auto-deduction on order close (backend-owned, not a screen);
purchase-order receiving (the purchasing module); per-ingredient valuation/costing and consolidated
multi-branch reporting; realtime/auto-refresh (manual refresh this slice).

## Capabilities

### New Capabilities
- `frontend-inventory`: the stock-control frontend — view branch stock and low-stock, set reorder
  thresholds, register in/out movements and physical recounts (attributed to an employee), and
  review per-ingredient movement history, all scoped to the active branch and gated by
  `inventory.read` / `inventory.adjust`, with ingredient names/units resolved from the recipes and
  catalog modules.

### Modified Capabilities
<!-- None. Consumes the existing inventory-management backend unchanged; ingredient/unit data is
     read-only from recipes-management and catalog-management, whose requirements are untouched. -->

## Impact

- **Frontend code**: new `front/src/services/inventory.api.ts`, `front/src/services/recipes.api.ts`
  (ingredients read only), `front/src/stores/inventory.ts`, `front/src/views/InventoryView.vue`, and
  `front/src/components/inventory/*`; a route in `front/src/router/index.ts` and a nav link in
  `front/src/components/AppSidebar.vue`. New tests under `front/src/services/__tests__` and
  `front/src/stores/__tests__`.
- **Reuses**: the catalog store (units → `unitName`), the staff store (employee picker for
  movements/recounts), the active-branch context, the shared `http` axios instance, and the
  `apiError` helpers.
- **Backend**: none — consumes existing `/inventory`, `/recipes/ingredients`, and `/catalog/units`
  endpoints.
- **Permissions/RBAC**: relies on `inventory.read` (screen + read) and `inventory.adjust`
  (threshold, movements, recounts); label data additionally reads `recipes.read` and `catalog.read`
  and degrades gracefully (short id ref) when those aren't granted. No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
