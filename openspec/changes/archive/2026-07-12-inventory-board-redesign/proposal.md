## Why

The Inventario redesign (approved as the design-only prototype at `/inventory/design`) gives the
back-office view the same clarity the dispatch board brought to operations: stats, combined
filters, a sortable table with the depletion bar (stock vs minimum at a glance), a detail drawer
and an alerts area. The prototype runs on mock "products"; the real domain is **insumos**
(ingredients + branch-scoped stock + movements). This change wires the board to that domain and
makes it *the* inventory screen at `/inventory` — scope **B** from exploration: wiring plus one
cheap backend column (`ingredients.category`) that unlocks the board's main filter.

## What Changes

- **Backend (small):** add a nullable `category` (≤50 chars) to `ingredients` + migration; expose
  it on the ingredient responses and accept it on create/PATCH in the recipes API. No new
  endpoints — filtering stays client-side.
- **Frontend:** port `InventoryDesignView` from mock state to the real domain via the existing
  `inventory` store (stock, movements, thresholds, recounts), `recipes` ingredients and `catalog`
  units. Domain adaptations agreed during exploration:
  - "Productos" becomes **"Insumos"**. Dropped from the UI: SKU, sale price, image upload,
    warehouse column, expiry section, and the Compras drawer tab (cut to a link to the
    purchasing screen later; no per-ingredient purchases endpoint exists).
  - Modal "Ajustar stock" maps Entrada→`registerMovement(in)`, Salida→`registerMovement(out)`,
    Ajuste→`recount` (already a first-class backend operation) — with the employee picker the
    current screen already uses.
  - Drawer "Alertas" tab keeps only the min-stock threshold (wired to `setThreshold`); the
    expiry alert config disappears with the expiry cut.
  - "Nuevo producto" becomes **"Nuevo insumo"** (2 steps): nombre + categoría + unidad →
    stock inicial (an `in` movement) + mínimo (threshold). Edit reuses the ingredient PATCH.
  - Alerts area keeps Agotados and Stock bajo; the Vencimiento section is removed.
- **Replace:** `/inventory` renders the board; the old `InventoryPanel`/`IngredientDetail`
  components, `inventoryDesignMock.ts` and the `/inventory/design` route are deleted.

### Explicit future work (out of scope, decided in exploration)

- **C2 — expiry:** simple per-stock expiry date (or lot tracking) + vencimiento alerts; the board
  reserves the visual slot.
- **C3 — canonical ingredient cost:** decide when recipe costing (BOM margin) lands; until then
  cost/supplier columns stay out.
- **C1 — warehouses:** per-warehouse stock only if a pilot needs it; a lightweight
  `storage_location` tag is the cheap alternative.

## Capabilities

### New Capabilities

None — both affected capabilities already exist.

### Modified Capabilities

- `recipes-management`: ingredients gain an optional `category` field (create/read/update).
- `frontend-inventory`: the InventoryView requirements change from the two-column list/detail to
  the board — stats summary, combined filters (category, stock state, search) with dismissable
  chips, sortable table with depletion bars and row tints, card view, detail drawer
  (Detalles/Movimientos/Alertas tabs), stock modal (entrada/salida/recuento), two-step ingredient
  modal, alerts area, bulk CSV export, and skeleton refresh. Existing permission gates
  (`inventory.read`/`inventory.adjust`) are preserved.

## Impact

- **Backend:** `modules/recipes/infrastructure/models.py`, one Alembic migration (0010),
  recipes API schemas + use case, recipes tests.
- **Frontend:** `views/InventoryDesignView.vue` (becomes the wired board),
  `views/InventoryView.vue` (replaced), `components/inventory/*` (deleted),
  `services/recipes.api.ts` (category field + create/update ingredient functions if missing),
  `stores/inventory.ts` (board helpers), `router/index.ts` (route cleanup), unit tests.
- **No breaking API changes** — only additive fields.
