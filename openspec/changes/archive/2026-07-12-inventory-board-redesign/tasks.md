# Tasks — inventory-board-redesign

## 1. Backend: ingredient category (additive)

- [x] 1.1 Add `category: Mapped[str | None] (String(50))` to `IngredientModel`; propagate through the domain entity and repository mapping; Alembic migration 0010
- [x] 1.2 Recipes API: `category` in ingredient responses and create/PATCH inputs (trimmed, ≤50); use case passes it through
- [x] 1.3 Backend tests: category round-trip on create/PATCH/list, absent category stays null; `ruff` + `mypy` pass; apply migration locally
- [x] 1.4 Seed touch-up: assign categories to the demo ingredients in `scripts/seed_demo.py` (idempotent) so the filter has real values

## 2. Frontend service + store

- [x] 2.1 `services/recipes.api.ts`: `category` on `Ingredient`; add `createIngredient`/`updateIngredient` functions if missing; service tests
- [x] 2.2 `stores/inventory.ts`: extend `StockRow`/ingredient index with category; add board helpers (status per row, distinct-categories getter, stats); write-through create/edit-insumo actions composing ingredient + initial movement + threshold; unit tests

## 3. Wire the board (in place at /inventory/design)

- [x] 3.1 Replace mock state in `InventoryDesignView.vue` with the `inventory`/`staff`/`branch` stores (branch-scoped load like the current screen); rename copy "productos"→"insumos"; drop SKU/precio venta/bodega/vencimiento/imagen columns and the Compras drawer tab
- [x] 3.2 Stats, filters (category from distinct values, stock state, search), chips, sorting and card view on real rows; depletion bar from `current_quantity`/`min_stock` (Decimal strings)
- [x] 3.3 Stock modal on real actions: Entrada/Salida → `registerMovement` (with the employee Select), Recuento → `recount`; friendly "no hay suficiente existencia" on 409/422; gates `inventory.adjust`
- [x] 3.4 Drawer wired: Detalles from row + ingredient, Movimientos from `listMovements` (employee names via staff), Alertas tab = threshold editor via `setThreshold`
- [x] 3.5 "Nuevo insumo" 2-step modal composing create ingredient → initial `in` movement → threshold, with partial-success copy; edit path reuses ingredient PATCH; gates `recipes.manage` (+`inventory.adjust` for stock steps)
- [x] 3.6 Alerts area (Agotados + Stock bajo) with restock CTAs; bulk bar + CSV export over real rows; skeleton refresh does a real reload

## 4. Swap and cleanup

- [x] 4.1 Verify end-to-end against the seeded backend (create insumo con stock inicial → aparece con barra y categoría; entrada/salida/recuento actualizan tabla e historial; umbral cambia el estado; filtros y export; read-only sin `inventory.adjust`)
- [x] 4.2 Point `/inventory` at the board; delete `/inventory/design` route (redirect), old `InventoryView.vue`, `components/inventory/*`, `lib/inventoryDesignMock.ts`; rename the view to `InventoryView.vue`
- [x] 4.3 Frontend quality gates: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`
