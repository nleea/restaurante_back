# Design — promote the Carta redesign

## Context

Two menu surfaces exist:

- **Production** — `views/MenuView.vue` + `components/menu/*`, wired through
  `stores/menu.ts`, `services/menu.api.ts`, `services/recipes.api.ts` to the real
  `/menu` and `/recipes` backends (categories, products, per-branch prices,
  variants, addons, ingredients, recipe BOM, missing-recipe guard).
- **Carta** — `views/CartaView.vue` + `components/carta/*` + `lib/carta.ts`, an
  in-memory prototype. Its signature is a **live food-cost meter** computed from
  per-ingredient `costPerUnit`.

The costing engine already exists in the `reports` module (`product-costing` spec):
ingredient unit cost = moving-average of purchasing `unit_price`; product cost =
BOM rollup; unavailable cost is surfaced as partial, never zero. It is exposed only
as period reports (COGS, channel/product margins in `reports.api.ts`).

## Decision 1 — how the food-cost meter gets cost

**Chosen: expose the existing moving-average ingredient unit cost as a menu-facing
read; keep the recipe-cost math on the frontend.**

`lib/carta.ts` already models exactly this: `costOf(insumo)` looks up a unit cost,
`recipeCost` sums `quantity × unitCost`, `foodCostPct` divides by price. We keep
that shape but feed it real numbers: the store loads a `{ ingredient_id → unit_cost
| null }` map (or `unit_cost` on ingredient reads), and the meter computes live as
lines change — no round-trip per keystroke.

- Alternative A — a per-variant `GET .../cost` endpoint. Rejected for now: forces a
  fetch on every recipe edit and duplicates the trivial rollup the client already
  does; the ingredient-cost map is cache-friendly and instant.
- Alternative B — a static `cost_per_unit` column on ingredients. Rejected: the
  project already committed (in `product-costing`) to moving-average from
  purchasing; a static column would be a second, conflicting source of truth.

**Honest partials.** When an ingredient has no purchase history its unit cost is
`null`. The meter must show "sin costo / margen parcial" and must not treat null as
0 — a zeroed cost reads as "100% margin" and would mislead pricing. This mirrors the
`cogs_partial` flag already used in reporting.

## Decision 2 — model mapping (prototype → real)

| Carta (`lib/carta.ts`) | Real backend / store | Mapping |
| --- | --- | --- |
| `Category.tag` (2-letter mark) | Category has no tag | derive `name.slice(0,2).toUpperCase()`; no column |
| `product.price + variant.extra` | per-branch `ProductPrice` + option-derived `extra_price` | read `priceByProductId`; variant extra from options |
| `Variant.recipe[]` by `insumo` name | `recipe_items` by `ingredient_id` + `unit_of_measure_id` | resolve names via `listIngredients()` |
| `Addition.appliesTo: all\|category` | addons attach **per product** | attach/detach; "all" = attach to each product (or keep a UI-level default) |
| `createInsumo(...)` | `POST /recipes/ingredients` | inline create keeps ingredient catalog authoritative |
| `make1to1(...)` (1:1 button) | ingredient + single recipe line qty 1 `und` | already specced in `frontend-menu` recipe editor |

The "additions applies-to-all" convenience is the one place the prototype is looser
than the backend; simplest is to resolve it to per-product attachment at save time.

## Decision 3 — retire vs redirect MenuView

**Chosen: the menu route renders the redesigned (Carta) screen; retire
`MenuView.vue` + `components/menu/*` once the recipe editor and price/variant/addon
management are all reachable in the new screen.** Keep the retirement in the same
change so we don't ship two menu screens. `frontend-menu` requirements (permission
gate, browse, manage categories/products/prices, recipe editor, stock guard) must
all still hold — they move to the new components, they don't disappear.

## Risks

- **Cost availability on a fresh tenant** — no purchases yet ⇒ every meter is
  partial. Acceptable and honest; the empty state must read as "add purchases to see
  costs," not as an error.
- **Feature parity** — the redesign must not drop any `frontend-menu` capability
  (esp. the recipe editor + stock guard just shipped). Verification checks each.
- **Additions semantics** — the applies-to-all shortcut needs a decided resolution
  before build; captured above as per-product attach.
