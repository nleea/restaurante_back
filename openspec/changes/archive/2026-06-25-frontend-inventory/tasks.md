## 1. Service layer

- [x] 1.1 Create `front/src/services/inventory.api.ts` with types `Stock` and `Movement` (quantity fields typed as `string`, matching backend schemas)
- [x] 1.2 Add stock calls: `listStock(branchId)`, `listLowStock(branchId)`, `getStock(branchId, ingredientId)`, `setThreshold(branchId, { ingredient_id, min_stock })`
- [x] 1.3 Add movement calls: `registerMovement(branchId, input)`, `recount(branchId, input)`, `listMovements(branchId, ingredientId)`
- [x] 1.4 Create `front/src/services/recipes.api.ts` with type `Ingredient` and `listIngredients(active?)` (`GET /recipes/ingredients`)
- [x] 1.5 Add service unit tests in `front/src/services/__tests__/inventory.api.spec.ts` and `recipes.api.spec.ts` (branch-scoped URLs, payloads, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/inventory.ts` (Pinia options) state: `stock`, `ingredientIndex`, `selectedIngredientId`, `movements`
- [x] 2.2 Add `loadBranch(branchId)` — fetch stock, build the `ingredient_id → { name, unitAbbr }` index from `listIngredients()` crossed with the catalog store's units (ensure units loaded)
- [x] 2.3 Add `selectIngredient(id)` (loads that ingredient's movement history) and `ingredientLabel(id)` getter with graceful fallback
- [x] 2.4 Add `setThreshold(ingredientId, minStock)` write-through (refetch stock)
- [x] 2.5 Add `registerMovement(input)` and `recount(input)` write-through (refetch stock + the affected ingredient's history)
- [x] 2.6 Add `rows` getter (stock joined to labels + a `low` flag = `current <= min`, ordered low-first then by name) and a `lowRows` getter
- [x] 2.7 Add store unit tests: stock load + index build, label resolution + fallback, low-flag computation and ordering, movement/recount/threshold write-through refetch

## 3. Screen, components, routing

- [x] 3.1 Add `/inventory` route (name `inventory`, `meta.permission: 'inventory.read'`) in `front/src/router/index.ts` and a nav link (`Inventario`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/InventoryView.vue` container + `InventoryPanel.vue` orchestrator: active-branch guard, load, manual refresh, error surface
- [x] 3.3 Create the Stock list (master): row per ingredient (name, unit, on-hand, reorder point), low-stock badge, "solo bajo stock" filter; drill-down on `< lg`
- [x] 3.4 Create the Ingredient detail: on-hand vs reorder point, set-threshold control (gated by `inventory.adjust`)
- [x] 3.5 Create the Registrar movimiento control (gated by `inventory.adjust`): type in/out, quantity, reason (presets + free), optional notes, employee picker (reuse staff store); friendly 409 "no hay suficiente existencia"
- [x] 3.6 Create the Recuento físico control (gated by `inventory.adjust`): counted quantity + employee picker → records the adjustment
- [x] 3.7 Create the movement history list (newest-first): type, quantity + unit, reason, timestamp
- [x] 3.8 Render quantities via a `formatQuantity` helper (trim trailing zeros, append unit abbreviation); surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: list stock → set a threshold (row flags low) → register in/out movements (on-hand updates; over-stock-out shows friendly conflict) → recount (adjustment recorded) → review history; verify a read-only user sees no adjust controls
