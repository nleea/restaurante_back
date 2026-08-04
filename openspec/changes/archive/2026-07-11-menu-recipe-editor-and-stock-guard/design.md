# Design — recipe editor + stock guard

## The invariant

```
active (sellable) variant  ⇒  has ≥1 recipe item

set is_active = true            → require ≥1 recipe item, else reject
delete the LAST recipe item     → reject if the variant is active (deactivate first)
new variant                     → born inactive (not sellable until it has a recipe)
add order item (safety net)     → reject if the variant has no recipe items
```

The guarantee we want: **nothing on sale can be sold without deducting stock.** The
load-bearing gate is at the sale boundary (order item add), but the primary UX gate
is at activation, so the user fails early in the menu rather than at the POS. The
delete-last-item guard keeps the invariant from being broken after activation.

## Where each guard lives (cross-module reads)

The codebase already reads recipe items across modules — `orders`'
`consume_inventory_for_order` queries `recipe_items`. We follow that pattern rather
than couple application services:

```
menu-product-variants   activate guard   → repo checks "variant has ≥1 recipe item"
recipes-management       delete-last guard → on delete, if it's the last item AND the
                                             variant is_active → reject
                         missing-recipe read → list active variants with 0 recipe items
order-management         add-item net      → repo checks "variant has ≥1 recipe item"
```

Each needs a small predicate `variant_has_recipe(tenant_id, variant_id) -> bool`
(SELECT EXISTS over `recipe_items`). It can be duplicated per module's repo (each
already touches its own tables) or centralized; duplication is fine and matches the
existing style.

## Recipe editor (frontend, in ProductDetail)

```
Producto ▸ [Variante ▾] ▸ RECETA
  ┌──────────────────────────────────────────────┐
  │  Insumo             Cant.  Unidad             │
  │  Carne molida       150    g       ✎  🗑      │  ← PATCH/DELETE /recipes/items/{id}
  │  Pan brioche          1    und     ✎  🗑      │
  │  ─────────────────────────────────            │
  │  + Añadir insumo   [buscar…]  [+ crear insumo]│  ← POST /recipes/variants/{id}/items
  │                                               │     (+ POST /recipes/ingredients inline)
  │  “Al vender 1 → descuenta 150 g carne, 1 pan” │
  │  [ Producto 1:1 ]                             │  ← create ingredient named as product + line qty 1
  └──────────────────────────────────────────────┘
  Estado de la variante:  ◯ Inactiva (sin receta)  →  al agregar la 1ª línea se puede activar
```

Data sources:
- Ingredient search/create → `GET/POST /recipes/ingredients` (already in `recipes.api.ts`).
- Recipe items → `GET /recipes/variants/{id}/items`, `POST /recipes/variants/{id}/items`,
  `PATCH /recipes/items/{id}`, `DELETE /recipes/items/{id}` (backend exists; add to the
  frontend service).
- Unit per line defaults to the ingredient's `unit_of_measure_id` (no conversion).

### The 1:1 button

For a can/bottle the "recipe" is the product itself: on click, create an ingredient
with the product's name and the base unit (`und`) if it doesn't exist, then add one
recipe line of quantity 1 referencing it. One click makes the variant deductible and
therefore activatable.

## Enforcement UX

- The variant's activate/"poner a la venta" toggle is disabled (with a tooltip) until
  the variant has a recipe; attempting it server-side returns a validation error that
  the UI surfaces.
- A "sin receta" badge on such variants and a small list (from the missing-recipe read)
  so legacy active-without-recipe variants — not auto-deactivated — are findable.

## Risks / assumptions

- **[assumption] No unit conversion.** Line unit = ingredient unit; `consume` multiplies
  quantities directly. Mixing units (kg recipe line vs g stock) would mis-deduct, so the
  editor locks the line unit to the ingredient's unit. Conversion is a separate change.
- **[assumption] Legacy active variants without a recipe are left as-is** and only listed;
  enforcing retroactively could pull items off sale unexpectedly.
- **[verify] Base unit `und` exists** in `units_of_measure` for the 1:1 shortcut (seed
  provides it; otherwise the shortcut creates/*requires* it).
- **[verify] Every sellable product already has ≥1 variant** (confirmed: variants are the
  sellable SKUs via `/menu/products/{id}/variants`); the editor always has a variant target.
- **[assumption] Deactivating a variant** is always allowed (removing it from sale never
  needs a recipe); only activation and the last-item delete are guarded.
