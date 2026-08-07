## Context

Fase 1 (`menu-appearance-presentation`, archived) built the appearance editor and the
`MenuAppearanceConfig` shape entirely on the frontend: `stores/menuAppearance.ts` holds
`published`/`draft`, boots from `mock/menuAppearance.ts`, and `publish()` copies draft→published
in memory. `lib/menuAppearance.ts:removableIngredientsFor` derives the "quitar" list from a
variant's recipe items (BOM). The backend menu module (FastAPI + SQLAlchemy 2.0 async, tenant
scoped by subdomain) exposes catalog CRUD but nothing for appearance; ingredients live in the
recipes module (`IngredientModel`, `TenantScopedMixin`). Migrations are sequential numbered files
(next is `0016`).

This change makes the config durable and closes the salt/oil noise in the removable list. The user
chose an **ingredient-level** `is_customer_removable` flag (global per insumo), not per recipe line.

## Goals / Non-Goals

**Goals:**
- One persisted appearance config per tenant, stored as the exact frontend `MenuAppearanceConfig`.
- `GET /menu/appearance` (default when absent) and `PUT /menu/appearance` (upsert), RBAC-gated.
- Frontend `load()`/`publish()` hit the API through the seam Fase 1 left; nothing else in the
  editor changes.
- `is_customer_removable` on ingredients (default true); removable derivation filters by it.

**Non-Goals:**
- No normalized appearance tables — the config is one JSONB document.
- No per-branch appearance (one public carta per tenant this phase).
- No storefront wiring (`/store` stays mock) and no removal→orders→KDS modifiers (separate change).
- No per-recipe-line removable flag (explicitly chosen against).

## Decisions

### Store the config as a single JSONB document, one row per tenant
The config is a presentation document the frontend owns and evolves as a unit; normalizing it into
tables would fight every shape change. A `menu_appearance` table with `(tenant_id unique, config
jsonb, timestamps)` keeps persistence a 1:1 mirror of `MenuAppearanceConfig`, so PUT is a whole-doc
upsert and GET returns the doc verbatim. Alternative (normalized theme/brand/blocks tables) —
rejected: high churn, no query benefit (always read/written whole).

### GET returns a computed default when no row exists
The editor and the future storefront should never handle a "not configured" 404. GET returns the
saved row or a backend-built default that mirrors `DEFAULT_THEME` + the mock default layout. The
default is **not** persisted on read (no write side effects on GET); the first PUT materializes it.

### Validate the config with a Pydantic schema mirroring the frontend types
`PUT` validates against a Pydantic model of `MenuAppearanceConfig` (theme/brand/blocks/dishCard/
dishDetail/blockContent) so a persisted document always has what consumers rely on; malformed
payloads get 422. The schema is the backend's copy of the shared contract — kept deliberately in
lockstep with `lib/menuAppearance.ts`.

### `is_customer_removable` lives on the ingredient (global), default true
Matches the stated pain: salt/oil are intrinsically non-removable regardless of dish. One column
on `ingredients`, surfaced through the existing ingredient create/update/list/retrieve. Default
`true` preserves current behavior (everything removable) until an admin curates staples off.
`removableIngredientsFor` (or its caller) filters recipe items to ingredients whose flag is true.
Alternative (per recipe line) — rejected by the user: more precise but adds per-line UI in the
recipe editor for a mostly ingredient-intrinsic property.

### Frontend change is confined to load/publish + the ingredient flag
`services/menuAppearance.api.ts` adds `getAppearance`/`putAppearance`. `load()` becomes async
(GET → published+draft, fallback to `mock`/defaults on failure so the editor still opens);
`publish()` awaits PUT then sets published. `Ingredient` gains `is_customer_removable`; the insumo
editor gets a toggle. No preview/panel rewrites — Fase 1 components are untouched.

## Risks / Trade-offs

- **JSONB drift from the frontend type** → a saved config could go stale as the shape evolves.
  Mitigation: Pydantic validation on write; treat `lib/menuAppearance.ts` as the source of truth
  and mirror it; tolerate unknown keys on read, fill missing with defaults.
- **`load()` becoming async can flash defaults before the GET resolves** → Mitigation: seed
  draft/published from defaults synchronously, then reconcile with the GET; isDirty only meaningful
  after load resolves.
- **Ingredient flag default true means existing tenants see no change** → intended; staples must be
  curated. Note in UI copy so admins know salt/oil won't hide until toggled.
- **A saved config referencing a since-deleted product/category** (e.g. gallery images) → the
  storefront/preview already reads live menu data and tolerates missing items; the config stores
  layout/style, not product copies, so drift is cosmetic.

## Migration Plan

Two DDL steps in one release: migration `0016` creates `menu_appearance` and adds
`ingredients.is_customer_removable boolean not null default true` (backfills existing rows to true
via the default). Additive and backward-compatible: pre-change frontends simply never call the new
endpoints. Rollback = down-migration drops the table and column; no data beyond saved configs is
affected. Optionally the demo seed writes one appearance row, but GET's default makes seeding
non-essential.

## Open Questions

- Should `PUT` return the full saved config (echo) or `204`? (Leaning: return the saved config, so
  the client re-syncs published from the server's canonical copy.) yes, put return the config
- Where exactly does the admin toggle `is_customer_removable` — the inventory/insumos board, the
  recipe editor's ingredient picker, or both? (Leaning: the insumo editor in the inventory board,
  where ingredients are already managed.), en donde se crea la receta 
