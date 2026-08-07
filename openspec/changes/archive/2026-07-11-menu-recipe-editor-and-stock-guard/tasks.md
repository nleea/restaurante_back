# Tasks — recipe editor + stock guard

## Backend — guards (reuse existing recipe_items / consume pattern)

- [x] Shared predicate `variant_has_recipe(tenant_id, variant_id) -> bool` (EXISTS over `recipe_items`) available to the menu/orders/recipes repos (duplicate per repo is fine)
- [x] `menu-product-variants`: block setting a variant `is_active = true` without a recipe → `ValidationError` "Registra la receta antes de ponerla a la venta."; new variants default inactive
- [x] `recipes-management`: on delete recipe item, if it is the LAST item AND the variant `is_active` → reject with a clear error ("desactiva la variante primero")
- [x] `recipes-management`: add a read of sellable (active) variants missing a recipe (for the "sin receta" list) — endpoint or filter
- [x] `order-management`: reject `add_item` when the variant has no recipe (safety net) → `ValidationError`
- [x] Tests: activate without recipe → blocked; activate with recipe → ok; delete last item of active variant → blocked; delete when inactive → ok; add order item for variant without recipe → blocked; missing-recipe read returns the right variants
- [x] `ruff check`, `mypy src`, `pytest tests/modules/menu tests/modules/recipes tests/modules/orders` green; check `seed_demo` variants stay activatable (they have BOM)

## Frontend — recipes service + store

- [x] Extend `services/recipes.api.ts` with BOM CRUD: `listRecipeItems(variantId)`, `addRecipeItem(variantId, {ingredient_id, quantity, unit_of_measure_id})`, `updateRecipeItem(itemId, patch)`, `deleteRecipeItem(itemId)`; keep the existing ingredient CRUD + `getRecipeCard`
- [x] Recipe store slice (or extend an existing store): hold a variant's items, load/mutate write-through, expose `hasRecipe(variantId)`; surface the missing-recipe list

## Frontend — recipe editor in the product detail

- [x] `components/menu/ProductDetail.vue` (or a child `RecipeEditor.vue`): per selected variant, list recipe lines with ingredient name + qty + unit; add line (ingredient search from the inventory directory, quantity, unit defaulted to the ingredient's unit); edit/delete lines; live "al vender 1 → descuenta …" preview
- [x] Inline "crear insumo" (calls `createIngredient`) so a missing ingredient can be added without leaving the editor
- [x] "Producto 1:1" button: create an ingredient named after the product (unit `und`) if absent + add a single recipe line qty 1
- [x] Activation UX: disable "poner a la venta"/activar while the variant has no recipe (tooltip), and surface the backend validation error if the guard trips; "sin receta" badge on such variants + a small list of sellable variants missing a recipe
- [x] Keep the El Pase visual language (tokens, mono figures) consistent with the menu screen
- [x] `pnpm type-check`, `pnpm lint`, `pnpm build` green

## Verification

- [x] Live: create a product + variant → try to activate → blocked; add a recipe (ingredient + qty) → activate → sell + close order → stock deducts and an inventory movement (reason `sale`) appears
- [x] Live: canned drink → "Producto 1:1" → activatable → sells and deducts the 1:1 ingredient
- [x] Live: delete the last recipe line of an active variant → blocked with the message
