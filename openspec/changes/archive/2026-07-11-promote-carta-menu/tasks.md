# Tasks — promote the Carta redesign to the production menu view

## Backend — expose ingredient unit cost for live editing (`product-costing`)

- [x] 1.1 Add a read that returns each ingredient's **unit cost** (the existing
  moving-average from purchasing) as `Decimal | null` (null when no purchase
  history) — reuse the cost logic already in the `reports` module; do not
  recompute or add a column. → `ingredient_unit_costs` repo method +
  `list_ingredient_costs` use case + `IngredientCost` entity.
- [x] 1.2 Expose it in a menu-facing shape: `GET /recipes/ingredient-costs` →
  `{ ingredient_id, unit_cost | null }[]`, gated under `recipes.read` (which menu
  editors already hold).
- [x] 1.3 Backend tests: ingredient with purchases → moving-average cost; ingredient
  with no purchases → `null` (not 0); read-permission gate (403 for cashier).

## Frontend — data layer

- [x] 2.1 Added `IngredientCost` type + `listIngredientCosts()` to `recipes.api.ts`.
- [x] 2.2 Extended `stores/menu.ts` with `ingredients`, `unitCostByIngredientId`,
  `costsLoaded` state; `fetchIngredients`/`loadIngredientCosts`/`createIngredient`
  actions; `ingredientName`, `unitCostOf`, `recipeCost(variantId)` getters.
- [x] 2.3 Ported the pure math to `lib/menuCosting.ts` (`healthOf`, `HEALTH_COPY`,
  `foodCostPct`, `marginOf`, `qty`, `money`); `recipeCost` getter returns a `partial`
  flag when any line's cost is null.

## Frontend — rewire the Carta components onto the store

- [x] 3.1 `FoodCostMeter.vue`: driven by the store helper; renders an honest
  "Sin precio"/"Costo parcial" state (no fabricated margin) when partial/unpriced.
- [x] 3.2 `VariantCard.vue`: recipe lines read/write through the store; ingredient
  picker from `store.ingredients`; unit from catalog units; 1:1 button kept;
  activation surfaces the 422 stock-guard.
- [x] 3.3 `CreateInsumoModal.vue`: name + unit → `store.createIngredient` (no cost
  input — cost derives from purchases); emits the new ingredient id.
- [x] 3.4 `ProductEditorModal.vue`: identity + category via store; per-branch price
  via `setPrice`; addons via attach/detach; two-phase create; stock-guard honored.
- [x] 3.5 `CategoriesTab.vue`: CRUD via store; mono `tag` derived from the name.
- [x] 3.6 `AdditionsTab.vue`: addon catalog CRUD (dropped `appliesTo`; per-product
  attach handled in the product editor).
- [x] 3.7 Removed `lib/carta.ts`. (Note: variant `extra_price` is display-only — it's
  server-derived from variant-option composition, out of this screen's scope.)

## Frontend — routing swap

- [x] 4.1 `/menu` now renders `CartaView.vue` (keeps `menu.read`); `/carta` redirects
  to `/menu` (canonical).
- [x] 4.2 Deleted `views/MenuView.vue` + all of `components/menu/*`; sidebar already
  pointed at `/menu` (label "Carta"). No lingering imports.

## Verification

- [x] 5.1 Every `frontend-menu` capability still holds on the new screen (verified by
  review): `menu.read` route gate kept; browse master–detail; manage
  categories/products/per-branch prices; recipe editor in VariantCard; stock guard
  (client pre-check + 422 surfaced) preserved.
- [x] 5.2 Food-cost meter shows a real margin for a costed dish and an honest
  "Sin precio"/"Costo parcial" state when partial/unpriced (no fabricated margin).
- [x] 5.3 `pnpm type-check`, `pnpm lint`, `pnpm test:unit` (296), `pnpm build` — all
  green (run independently).
- [x] 5.4 Backend `pytest` green: 3 new ingredient-cost tests + full suite (259),
  ruff + mypy clean.
- [ ] 5.5 Live E2E against a running backend (open product → edit recipe → watch meter
  → set price → activate). Requires the full stack up (Postgres + seed + uvicorn +
  dev server) — pending a live smoke run.
