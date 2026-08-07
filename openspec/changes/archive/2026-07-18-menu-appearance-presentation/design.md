## Context

`/menu/appearance` (`MenuAppearanceView.vue` + `components/menu-appearance/*`) is a working,
mock, two-pane editor: an editor column (Tema / Marca / Bloques tabs) and a live phone preview.
State lives in `stores/menuAppearance.ts` as two copies of `MenuAppearanceConfig`
(`draft` / `published`) with `isDirty` and a local `publish()`. The geometry/model lives in
`lib/menuAppearance.ts` (4-col grid, block sizes, collision, `gridToLinearOrder`).

Two gaps motivate this change: (1) `MenuPreview.vue` renders hardcoded `DISHES`/`FEATURED`
arrays; (2) the admin cannot configure how a dish is presented or how the dish-detail screen is
laid out, and only five layout blocks exist. Real product data already lives in
`stores/menu.ts` (`products`, `categories`, `priceByProductId`, `addons`, and per-variant
`recipeItemsByVariantId` with an `ingredientName` resolver). This phase is presentation-only
and stays entirely in the frontend; persistence is a separate follow-up change.

## Goals / Non-Goals

**Goals:**
- Feed the preview from the real `menu` store instead of hardcoded constants.
- Add `dishCard` (global card style + field toggles) and `dishDetail` (ordered, toggleable
  sections) to the config, each with an editor panel and a live preview.
- Derive the dish-detail removable-ingredient list from a product's recipe (BOM) as a
  subtractive-only exclusion, keeping the recipe untouched and additions confined to addons.
- Add four layout blocks — `promo`, `hours`, `gallery`, `testimonials` — reusing the existing
  grid engine and hidden-tray flow.
- Keep the draft/published in-memory model and the one-file-swap `publish()` seam.

**Non-Goals:**
- No `menu_appearance` table, GET/PUT, or any backend/API change (Fase 2).
- No `customer_removable` flag on insumos; this phase derives from the full BOM (Fase 2 refines).
- No wiring of removals into orders/KDS; that belongs to the storefront→order flow, not here.
- No change to the production carta (`frontend-menu`) or the `/store` storefront.

## Decisions

### `dishDetail.sections` reuses the block-ordering pattern, not the 2D grid
The detail screen is a single vertical column, so its sections are modeled as an **ordered list
of `{ id, visible }`** (like a simplified `blocks`) rather than an `x/y/size` grid. The
dish-detail preview iterates that array directly — no new geometry code. Alternative: a second
grid canvas — rejected as overkill for a one-column screen.

### `dishCard` is one global object, not per-product
The card style and field toggles are a tenant-wide presentation choice ("set once, all dishes
inherit"), matching the user's "que no tengan que crearlo una y otra vez". Per-product overrides
are explicitly out of scope. This keeps `dishCard` a small flat object in the config and avoids
touching the product model.

### Removable ingredients are derived, read-only, at preview time
The preview resolves a dish's variant → `recipeItemsByVariantId` → `ingredientName`, producing a
display-only list. Nothing writes back to recipes. The **subtractive-only invariant is
structural**: the "quitar" UI offers keep/exclude checkboxes with no quantity control, while the
addons list is a separate priced lane — so "add more of a base ingredient" is unrepresentable by
construction. This is the cleanest way to honor the KDS rule ("removed can't be re-added except
as addon") without new data.

### Preview data loading is read-only reuse of the menu store
`MenuPreview` (and the detail preview) call existing menu-store getters/actions
(`fetchCategories`, `fetchProducts`, `loadPrices`, `fetchAddons`, `loadVariants` +
`loadRecipeItems` for the opened sample dish). No new API layer; the appearance store never
writes menu data. A single representative product drives the detail preview to avoid loading
every variant's recipe.

### New blocks extend the existing enums, content lives in the config
`BlockId` gains `promo | hours | gallery | testimonials`; `BLOCK_META` gains their label/icon/
blurb; `SIZE_CELLS`/collision/tray need no change. Editable text/image for promo/hours/
testimonials is held in a `blockContent` slice of the config (keyed by block id) so it travels
with draft/published. `gallery` reads product `image_url`s at render time plus any config-held
image list.

## Risks / Trade-offs

- **BOM has non-removable insumos (sal, aceite)** → deriving the full recipe can surface
  nonsensical "quitar sal". Mitigation: acceptable in this mock phase; Fase 2 adds a
  `customer_removable` flag. Note it in UI copy if it looks odd in the demo.
- **Preview loading real menu data adds async + failure states** → Mitigation: neutral
  placeholder when unloaded (spec'd), and read-only reuse of the already-hardened menu store.
- **Config shape grows** → risk of drifting from the eventual DB schema. Mitigation: keep new
  sections as plain serializable objects; `publish()` stays the single write seam so Fase 2 maps
  the same shape to a JSON column.
- **`dishDetail` ordering vs `blocks` ordering are similar but separate** → mild duplication.
  Mitigation: factor a tiny shared "ordered sections" helper if it reads cleanly; otherwise keep
  them independent to avoid over-abstraction.

## Migration Plan

Pure additive frontend change, no data migration. New config sections are seeded in
`mock/menuAppearance.ts` so existing behavior is unchanged and the panel boots populated.
Rollback = revert the frontend commit; nothing persisted.

## Open Questions

- Card styles: is `list / card / grid` the right trio, or is a fourth (`hero`) wanted? (Design
  assumes three; easy to extend.) las 4, o si es mucho trabaja las 3 primeras
- Gallery source: product photos only, standalone uploads only, or both? (Design allows both;
  uploads reuse the existing `ImageUploadMock`.), las fotos vienen de la carta creada, puede a ver varias asi que tiene que soportarlo
- Should the dish-detail preview be a toggle inside the phone frame or a separate second frame
  alongside the carta preview? (Leaning: a "ver detalle" toggle within the same frame.), toggle dentro del mismo frame, pero que se pueda dar atras sin perder nada
