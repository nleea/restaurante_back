## Context

The backend `/inventory` module is complete but unconsumed. Its contract (every path branch-scoped):

- **Stock**: `GET /inventory/branches/{b}/stock` (list), `GET /inventory/branches/{b}/stock/low`
  (at-or-below threshold), `GET /inventory/branches/{b}/stock/{ing}` (one),
  `PUT /inventory/branches/{b}/stock/threshold` (`{ ingredient_id, min_stock }`). Perm
  `inventory.read` (read) / `inventory.adjust` (threshold).
- **Movements**: `POST /inventory/branches/{b}/movements`
  (`{ ingredient_id, employee_id, type: "in"|"out", quantity, reason, reference_id?, notes? }`),
  `POST /inventory/branches/{b}/recounts`
  (`{ ingredient_id, employee_id, counted_quantity, reason?, notes? }`),
  `GET /inventory/branches/{b}/movements/{ing}` (history, newest-first). Perm `inventory.adjust`
  (writes) / `inventory.read` (history).
- `Stock = { id, branch_id, ingredient_id, current_quantity, min_stock, updated_at }`.
- `Movement = { id, branch_id, ingredient_id, type, reason, quantity, employee_id, reference_id,
  notes, created_at }`.
- Quantity fields are server-side `Decimal`, serialized as **strings**.

Three facts drive the design: (1) **stock and movements name only `ingredient_id`** — names and
units live in other modules, so labels are resolved client-side from `GET /recipes/ingredients`
(`{ id, name, unit_of_measure_id, is_active }`) crossed with the catalog units the existing catalog
store already loads (`unitName`/abbreviation); (2) **quantities are physical units, not money** — so
they render as plain decimals with the ingredient's unit (never `formatCOP`), trimming insignificant
trailing zeros; and (3) writes are **attributed to an employee**, so the screen reuses the staff
picker exactly as the cash screen does. The frontend stack and conventions follow the existing
screens (Vue 3 `<script setup>`, Pinia options stores, PrimeVue + Tailwind, the shared `@/lib/http`
axios instance, active-branch scope, mobile-first master–detail as in Staff/Cash).

## Goals / Non-Goals

**Goals:**
- A self-sufficient stock-control screen: see on-hand and what's below its reorder point, set
  thresholds, register receipts/consumption, perform physical counts, and review per-ingredient
  history — all branch-scoped.
- Resolve readable ingredient labels (name + unit) with graceful fallback, reusing recipes +
  catalog data rather than new infrastructure.
- Mirror the established store discipline (write-through, `can()` gating) and the staff employee
  picker for attribution.

**Non-Goals:**
- Ingredient CRUD (owned by the recipes module — this screen reads the directory only).
- The orders→recipes→inventory auto-deduction on order close (backend-owned, not a screen).
- Purchase-order receiving (purchasing module), valuation/costing, consolidated multi-branch
  reporting, and realtime/auto-refresh (manual refresh this slice).

## Decisions

**1. One `InventoryView`, master–detail, like Staff/Cash.** A stock list (master) with a low-stock
filter, and a per-ingredient detail (on-hand vs threshold, the three write actions, and history).
On `< lg` the list fills the screen and tapping a row drills into a full-screen detail; on `>= lg`
both panes show. Rejected: separate list/adjust screens — the detail is where every action and the
history naturally live together.

**2. Quantities stay string-decimal; the only client logic is the low-stock flag.** A small
`formatQuantity(value)` renders the decimal trimmed of trailing zeros and pairs it with the unit
abbreviation; no money formatter touches stock. The low-stock flag is `Number(current) <=
Number(min)` computed once per row. The backend also exposes a `/stock/low` endpoint; the client
filters the already-loaded `stock` rather than a second fetch (one list, client filter — the same
"single fetch, derive client-side" choice the kitchen board made for columns), keeping the list and
the filter perfectly consistent.

**3. Ingredient directory resolved client-side, reusing recipes + catalog.** The store builds an
`ingredient_id → { name, unitAbbr }` index from `listIngredients()` crossed with the catalog store's
units. A new minimal `recipes.api.ts` exposes just `listIngredients` (the only recipes read this
slice needs) rather than a whole recipes store. When an ingredient or unit can't be resolved (e.g.
the user lacks `recipes.read`/`catalog.read`, or the ingredient was deactivated) the row falls back
to a short `#<id slice>` ref and an em-dash unit — best-effort, never broken.

**4. Writes reuse the staff employee picker.** `employee_id` on movements/recounts is chosen from
the staff store's active-branch employees (load on demand, `ensureLoaded`), exactly as the cash
screen does. An empty staff list surfaces a friendly hint rather than a broken submit.

**5. Store shape parallels `cash.ts`/`kitchen.ts`.** State: `stock: Stock[]`, `ingredientIndex:
Record<string, { name, unitAbbr }>`, `selectedIngredientId`, `movements: Movement[]` (the selected
ingredient's history). Getters: `rows` (stock joined to labels + a `low` flag, ordered low-first
then by name), `lowRows`, `ingredientLabel(id)`. Actions (each write-through): `loadBranch(branchId)`
(stock + ingredient index + units), `selectIngredient(id)` (loads history), `setThreshold`,
`registerMovement`, `recount` — the three writes refetch stock and the affected ingredient's history.

**6. Permission model mirrors existing screens.** Route guard `meta.permission: 'inventory.read'`;
within the view, `auth.can('inventory.adjust')` gates every mutate control (threshold, movement,
recount). Read-only users see stock and history without action affordances. The backend enforces the
same permissions regardless.

## Risks / Trade-offs

- **Label resolution is best-effort** → an ingredient not in the directory (deactivated, or no
  `recipes.read`) shows a short ref. → Mitigation: load the directory + units when the screen opens
  and degrade clearly; stock is still actionable by id.
- **Client low-stock filter vs the `/stock/low` endpoint could diverge** if the backend's rule
  changes → Mitigation: the rule (`current <= min`) is simple and stable; filtering the one loaded
  list keeps list/filter consistent and avoids a second fetch. Revisit only if the rule grows.
- **Stock-out beyond on-hand returns a conflict** → Mitigation: catch 409 on movement submit and
  show "no hay suficiente existencia"; keep the form values for correction.
- **Decimal display** (units can be fractional, e.g. 1.5 kg) → Mitigation: `formatQuantity` trims
  trailing zeros but preserves real fractions; never rounds to integers like the money formatter.
- **Many reads on open** (stock + ingredients + units, then history on select) → bounded by the
  pilot's catalog size; the same `Promise.all` fan-out as the other screens.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`inventory.read` / `inventory.adjust` permissions. Rollback = revert the new files, the router entry,
and the nav link; no persisted client state.

## Open Questions

- Should the list paginate/search when the ingredient catalog grows large? Deferred — the pilot's
  catalog is small; a client search box can be added without backend changes.
- Should movement `reason` be a controlled vocabulary (received, waste, transfer, …) rather than free
  text? The backend accepts a free 1–50 char string; the UI offers common presets plus free entry,
  left non-binding this slice.
