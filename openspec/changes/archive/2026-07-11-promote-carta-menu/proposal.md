# Promote the Carta redesign to the production menu view

## Why

The menu screen was redesigned as **Carta** (`/carta`) — a full-screen product
editor whose hero is a **live food-cost meter**: as you build a variant's recipe,
its cost, margin and food-cost % update and glow calm → warm → hot. It's the
sharpest menu-management surface we have, but it runs entirely in-memory
(`lib/carta.ts`, mock data). Meanwhile the real menu (`MenuView.vue` +
`components/menu/*`) is fully backend-wired but plainer, and the two have drifted.

We want **one** menu view: the Carta design, backed by the real data. The good
news from exploring: almost everything Carta needs already exists on the backend
(`/menu`, `/recipes`) and in the production store (`stores/menu.ts`,
`recipes.api.ts`). The one true gap is cost — and even that engine already exists:
`product-costing` (in the `reports` module) already computes ingredient unit cost
as the **moving-average of purchase prices** and rolls the BOM up to product cost.
It is only exposed period/report-shaped (COGS, P&L), not as a live per-ingredient
cost at edit time. So this change is mostly a **frontend rewire** plus a **small
read** that surfaces the cost we already compute.

## What Changes

**Backend (`product-costing`)** — surface existing costs for live editing
- Expose **ingredient unit cost** (the moving-average already computed from
  purchasing) as a menu-facing read the editor can call — e.g. a cost map over
  ingredients, or a `unit_cost` field on ingredient reads. Unavailable cost stays
  **null/partial, never zeroed** (mirrors the existing product-costing contract).
- No new costing math, no new column, no schema migration for cost.

**Frontend (`frontend-menu`)** — the redesigned screen becomes the real one
- Rewire the Carta components (`components/carta/*`: `ProductEditorModal`,
  `VariantCard`, `FoodCostMeter`, `CategoriesTab`, `AdditionsTab`,
  `CreateInsumoModal`) onto `stores/menu.ts` + `recipes.api` + the new cost read,
  replacing the in-memory `lib/carta.ts` singleton.
- The **food-cost meter** computes live from real ingredient unit cost × recipe
  quantities and the product's active-branch price; shows an honest "sin costo /
  parcial" state when cost is unavailable instead of a misleading margin.
- Map the prototype's simplified model to the real one: category `tag` derived from
  the name (no new column), price via per-branch `ProductPrice`, additions via the
  existing addon attach/detach, recipe lines via `ingredient_id` + unit.
- The menu route serves the redesigned screen; the old `MenuView` +
  `components/menu/*` are retired (or the route redirects to it).

## Impact

- Specs: `product-costing` (ADDED read), `frontend-menu` (MODIFIED presentation +
  live cost meter).
- Code: `front/src/services/*.api.ts` (cost read), `stores/menu.ts` (cost state),
  `components/carta/*` (rewired to store), `router/index.ts` (route swap),
  `views/CartaView.vue` → becomes the menu view; `views/MenuView.vue` +
  `components/menu/*` retired. Backend: one read in the costing/recipes surface.
- Preserves the stock-guard invariant already in place (a variant sells only with a
  recipe).

## Out of scope

- Changing how ingredient cost is calculated (moving-average from purchasing stays).
- Unit conversion in recipes (a line uses the ingredient's own unit, unchanged).
- Per-branch cost variation; cost is tenant-level as today.
- Any new costing/COGS reporting — this only *reads* what already exists.
