## Why

Fase 1 gave admins a rich appearance editor (theme, brand, layout blocks, dish-card style,
dish-detail layout) — but everything lives in memory: reload the page and the work is gone, and
the public storefront has no saved config to read. This change persists the appearance config to
the database so it survives reloads and becomes the shared contract the storefront will consume.
It also removes the one honesty gap Fase 1 flagged: the "quitar ingredientes" list derives from
the whole recipe (BOM), so non-removable staples like salt and oil show up as removable.

## What Changes

- **New `menu_appearance` table** (tenant-scoped, one row per tenant) storing the whole
  `MenuAppearanceConfig` as a JSONB document — the same shape the frontend already owns.
- **New endpoints** under the menu module: `GET /menu/appearance` (returns the saved config, or
  a computed default when none exists) and `PUT /menu/appearance` (upserts the config).
  `GET` requires `menu.read`, `PUT` requires `menu.manage`.
- **Frontend store wiring**: `load()` GETs the saved config instead of the mock; `publish()` PUTs
  the draft (the one-file-swap seam Fase 1 preserved). Discard/isDirty are unchanged.
- **`is_customer_removable` flag on ingredients** (default `true`): ingredient create/update/read
  carry it, so staples can be marked non-removable once and excluded everywhere.
- **Removable derivation honors the flag**: the dish-detail preview's "quitar ingredientes" list
  keeps only recipe ingredients whose ingredient is `is_customer_removable`.
- The admin can toggle `is_customer_removable` from the insumo editor.

Out of scope (a later, separate change): sending structured removal modifiers from the storefront
into orders → KDS; wiring the public `/store` to the persisted config (still mock).

## Capabilities

### New Capabilities
- `menu-appearance`: backend persistence of the public-carta appearance config — a tenant-scoped
  `menu_appearance` table holding the config as JSONB, with `GET`/`PUT /menu/appearance`
  (read/manage gated) and a sensible default when a tenant has never saved one.

### Modified Capabilities
- `frontend-menu-appearance`: `load()`/`publish()` move from mock to the real appearance API; the
  removable-ingredient derivation filters by `is_customer_removable`.
- `recipes-management`: ingredients gain an `is_customer_removable` flag (default true) across
  create/update/list/retrieve.

## Impact

- **Backend** (`../backend`):
  - New migration `0016_menu_appearance` (create `menu_appearance`) and a column add to
    `ingredients` (`is_customer_removable boolean not null default true`).
  - Menu module: new `MenuAppearanceModel`, repository, use case, Pydantic schema for the config,
    and the two router endpoints; a default-config builder mirroring the frontend defaults.
  - Recipes module: `IngredientModel.is_customer_removable`, surfaced in ingredient schemas,
    use cases, and repository.
- **Frontend** (`front/src`):
  - `services/menuAppearance.api.ts` (new): typed `getAppearance` / `putAppearance`.
  - `stores/menuAppearance.ts`: `load()` async GET (fallback to defaults on 404/empty),
    `publish()` async PUT; keep draft/published/isDirty.
  - `services/recipes.api.ts` + `stores/menu.ts`: `is_customer_removable` on `Ingredient`;
    `removableIngredientsFor` (or its caller) filters by it.
  - Insumo editor gains a "quitable por el cliente" toggle.
- **Contract**: the persisted JSONB shape MUST match the frontend `MenuAppearanceConfig` so the
  future storefront reads the same object the admin writes.
