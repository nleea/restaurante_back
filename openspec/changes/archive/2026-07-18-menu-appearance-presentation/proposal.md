## Why

The `/menu/appearance` editor lets an admin shape the public carta's theme, brand, and a
grid of layout blocks — but the live preview paints hardcoded sample dishes, and the admin
has no control over **how a dish is presented** (card style, which fields show) or **how the
dish-detail screen is laid out**. The customer-facing storefront brief calls for exactly this
per-dish configuration, and for a richer set of page blocks (promo, hours, gallery,
testimonials). This is the presentation half of the work; persistence to a DB comes in a
follow-up change.

## What Changes

- The appearance **preview reads real menu data** (categories, products, prices, addons) from
  the menu store instead of the hardcoded `DISHES`/`FEATURED` constants.
- New **`dishCard` config**: a global card style (`list` / `card` / `grid`) plus per-field
  visibility toggles (image, description, price, addon hint, removable hint). Applies to every
  dish; the admin sets it once.
- New **`dishDetail` config**: an ordered, toggleable list of detail sections
  (photo · description · variants · addons · **remove** · note) — same ordering engine already
  used for layout blocks — with a live detail preview.
- **Removable ingredients** surface in the detail preview, **derived from the product's recipe
  (BOM)**. They are a per-order-line exclusion, never a change to the recipe. Excluding an
  ingredient can only ever remove; adding is exclusively the addons lane (this invariant is
  enforced by construction — the two UIs are disjoint).
- **Four new layout blocks** available on the canvas: `promo`, `hours`, `gallery`,
  `testimonials`, each with admin-editable content held in the config (gallery can pull product
  `image_url`s).
- Everything stays **mock/in-memory** (draft/published copies), matching the current store;
  `publish()` remains a local copy so wiring the API later is a one-file change.

## Capabilities

### New Capabilities
- `frontend-menu-appearance`: the admin editor for the public carta's presentation — theme,
  brand, layout blocks (now including promo/hours/gallery/testimonials), global dish-card style,
  and dish-detail layout — with a live preview fed by real menu data. Mock persistence.

### Modified Capabilities
<!-- No existing spec's requirements change; the production carta (frontend-menu) and storefront are untouched. -->

## Impact

- **Frontend only.** No backend or API changes in this phase.
- New/changed code under `front/src/`:
  - `lib/menuAppearance.ts` — extend `MenuAppearanceConfig` with `dishCard` and `dishDetail`;
    add the four new `BlockId`s + their `BLOCK_META`; a helper to derive removable ingredients
    from a variant's recipe items.
  - `stores/menuAppearance.ts` — draft mutations for `dishCard`, `dishDetail`, and the new
    blocks; read-through of the `menu` store for real preview data.
  - `mock/menuAppearance.ts` — seed the new config sections.
  - `components/menu-appearance/*` — new panels (DishCardPanel, DishDetailPanel), new preview
    renderers for the four blocks + a dish-detail preview; `MenuPreview` switches to real data.
- Reads (no writes) from the existing `menu` store: `products`, `categories`, prices, `addons`,
  and per-variant `recipeItems` for the removable-ingredient derivation.
- Gated by `menu.manage` (unchanged).
- Out of scope (deferred to Fase 2): the `menu_appearance` persistence table + GET/PUT, the
  `customer_removable` insumo flag, and sending structured modifiers to orders/KDS.
