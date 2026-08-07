## 1. Model & config shape (lib/menuAppearance.ts)

- [x] 1.1 Add `DishCardStyle = 'list' | 'card' | 'grid'` and a `DishCardConfig` interface
  (`style` + `show: { image, description, price, addonHint, removableHint }`).
- [x] 1.2 Add `DishDetailSectionId` (`photo|description|variants|addons|remove|note`) and a
  `DishDetailConfig` as an ordered `{ id, visible }[]`.
- [x] 1.3 Extend `BlockId` with `promo | hours | gallery | testimonials`; add their entries to
  `BLOCK_META` (label/icon/blurb) and to `BLOCK_ORDER`.
- [x] 1.4 Add a `blockContent` slice type (per-block editable text/image for promo/hours/
  testimonials, and an optional gallery image list) and fold it into `MenuAppearanceConfig`
  alongside `dishCard` and `dishDetail`.
- [x] 1.5 Add `DEFAULT_DISH_CARD` / `DEFAULT_DISH_DETAIL` defaults and a helper
  `removableIngredientsFor(variantId, menuStore)` that maps recipe items → ingredient names
  (read-only, returns `[]` when no recipe).
- [x] 1.6 Update `lib/__tests__/menuAppearance.spec.ts`: keep grid geometry green with the new
  block ids; add a test for the removable-ingredient derivation helper.

## 2. Store (stores/menuAppearance.ts) & mock seed

- [x] 2.1 Add draft mutations: `updateDishCard(patch)`, `toggleDishCardField(field)`,
  `setDishDetailOrder(sections)`, `toggleDishDetailSection(id)`, and content setters for the
  new blocks (`updateBlockContent(id, patch)`).
- [x] 2.2 Ensure `isDirty` / `discard` / `publish` cover the new config sections (they compare
  the whole config, so verify no field is excluded from clone/serialize).
- [x] 2.3 Seed `mock/menuAppearance.ts` with `dishCard`, `dishDetail`, the four new blocks
  (hidden by default in the tray), and sample `blockContent`.

## 3. Real menu data in the preview

- [x] 3.1 On `MenuAppearanceView` mount, load menu data read-only via the `menu` store
  (`fetchCategories`, `fetchProducts`, `loadPrices(activeBranch)`, `fetchAddons`); guard for the
  not-yet-loaded state.
- [x] 3.2 Rewrite `MenuPreview.vue` `full_menu` + `featured_categories` blocks to render real
  categories/products/prices instead of `DISHES`/`FEATURED`; show a neutral placeholder while
  loading.
- [x] 3.3 Pick one representative product for the detail preview; lazily `loadVariants` +
  `loadRecipeItems` for it so removable ingredients resolve.

## 4. Dish-card presentation

- [x] 4.1 Build `DishCardPanel.vue`: style selector (`list/card/grid`) + field toggles, bound to
  the store mutations.
- [x] 4.2 Render the three card styles in `MenuPreview` driven by `dishCard.style`, honoring each
  `show.*` toggle (image, description, price, addon hint, removable hint).
- [x] 4.3 Add a "Plato" (dish) tab to `MenuAppearanceView` grouping the card + detail panels.

## 5. Dish-detail layout

- [x] 5.1 Build `DishDetailPanel.vue`: reorder (up/down or drag) + visibility toggles over
  `dishDetail.sections`.
- [x] 5.2 Build a dish-detail preview (toggle within the phone frame) that renders sections in
  configured order/visibility: photo · description · variants · addons · remove · note.
- [x] 5.3 Render the `remove` section as keep/exclude checkboxes from `removableIngredientsFor`,
  with no add/quantity control; render `addons` as the separate priced lane.

## 6. New layout blocks

- [x] 6.1 Add `promo`, `hours`, `gallery`, `testimonials` to `HiddenBlocksTray` (they inherit
  the existing drag-from-tray → canvas flow with no new geometry).
- [x] 6.2 Add preview renderers for each new block in `MenuPreview`, reading `blockContent`;
  `gallery` displays product `image_url`s (plus any config images).
- [x] 6.3 Add lightweight content editors for promo/hours/testimonials (reuse `ImageUploadMock`
  for images) wired to `updateBlockContent`.

## 7. Verify

- [x] 7.1 `pnpm type-check` and `pnpm lint` clean.
- [x] 7.2 `pnpm test:unit` green (geometry + removable-ingredient helper).
- [ ] 7.3 Manual pass at `demo.localhost:5173/menu/appearance`: preview shows real dishes; card
  style/field toggles apply live; detail sections reorder/hide; removable ingredients come from a
  real recipe and are exclude-only; all four new blocks place and render; publish/discard behave.
