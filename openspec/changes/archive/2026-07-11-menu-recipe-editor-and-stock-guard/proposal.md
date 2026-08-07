# Recipe editor + stock guard: no variant sells without a recipe

## Why

Today a product can be created and sold with **no recipe (BOM)**, and the backend
has no UI to register one — `recipes.api.ts` is read-only for the BOM. When an
order closes, `consume_inventory_for_order` deducts stock only for variants that
have recipe items; a variant with none deducts **nothing, silently**. So new
products (including canned drinks) sell without touching inventory, and there is
no place in the app to fix it. This makes inventory untrustworthy — the same
class of silent no-op we just closed for order payments.

## What Changes

Every sellable variant must carry a recipe that ties it to inventory, editable in
the app, and a variant cannot go on sale without one.

**Frontend (`frontend-menu`)** — the main build
- A **Recipe editor** inside the product detail, per selected variant: search an
  ingredient from the inventory directory (or create one inline), set quantity and
  unit, list the lines, edit/delete them, and preview "sells 1 → deducts X of Y".
- A **1:1 button** for cans/bottles: creates an ingredient named after the product
  and a single recipe line of quantity 1 (unit `und`), in one click.
- The activation control refuses to put a variant on sale without a recipe, and a
  "sin receta" signal / list surfaces sellable variants that are missing one.
- Extend `recipes.api.ts` with the BOM CRUD (add/list/update/delete recipe items) —
  the backend endpoints already exist.

**Backend guards — "active ⇒ has recipe"**
- `menu-product-variants`: a variant cannot be set `is_active = true` unless it has
  at least one recipe item; new variants default inactive.
- `recipes-management`: deleting the **last** recipe item of an **active** variant
  is rejected (deactivate first); add a read of "sellable variants missing a recipe".
- `order-management`: adding an order item whose variant has no recipe is rejected
  (a safety net; normally unreachable since only active variants are sold).

Units: a recipe line uses the ingredient's own unit; `consume_inventory_for_order`
does not convert units (`line.quantity × item.quantity`), so unit conversion stays
out of scope.

## Impact

- Specs: `frontend-menu`, `menu-product-variants`, `recipes-management`,
  `order-management`.
- Backend: guards in menu/recipes/orders use cases + repos (cross-module reads of
  recipe items, following the existing `consume_inventory_for_order` pattern). No
  new tables; reuses `recipe_items`, `ingredients`, `product_variants`. Tests.
- Frontend: `recipes.api.ts` BOM CRUD + a recipe store slice + the editor UI in
  `components/menu/*` (ProductDetail) + the activation/"sin receta" affordances.

## Out of scope

- Unit-of-measure conversion in deduction (line unit = ingredient unit for now).
- Retroactive enforcement on existing active variants (surfaced via the "sin
  receta" list, not auto-deactivated).
- Recipe cost/costing UI (COGS already computes from the BOM elsewhere).
- Yield/sub-recipes (a recipe referencing another recipe).
