## Context

The approved prototype lives at `/inventory/design` (`front/src/views/InventoryDesignView.vue` +
`front/src/lib/inventoryDesignMock.ts`): stats, filters with chips, sortable table with the
depletion-bar signature (notched bar, minimum at the midpoint), card view, detail drawer, stock
modal, 2-step product modal, alerts area. It was built around mock "products" with fields the
real domain doesn't have.

The real domain, mapped in exploration:

- `ingredients` (recipes module): `name`, `unit_of_measure_id`, `is_active` — full CRUD at
  `/recipes/ingredients` (`recipes.read`/`recipes.manage` gates). No category/SKU/cost/image.
- `inventory_stock` (branch-scoped): `current_quantity`, `min_stock`, `updated_at` (Decimal
  strings kept verbatim in transit).
- `inventory_movements`: `type` (`in`/`out`/`adjustment`), free-text `reason`, `quantity`,
  `employee_id`, `notes`, `created_at`. Adjustment happens through the dedicated `recount`
  endpoint (counted quantity, not delta).
- The `inventory` Pinia store already loads stock + resolves ingredient names/units
  (recipes × catalog) and holds write-through actions; the current screen's stock modal already
  uses an employee Select for `employee_id`.

## Goals / Non-Goals

**Goals:**

- The board at `/inventory` runs entirely on real branch-scoped data with the approved layout,
  the depletion bar intact (stock vs min are both real), and the existing permission gates.
- One additive backend change only: `ingredients.category`, unlocking the board's main filter.
- Honest domain language: insumos, not productos.
- Delete the prototype route/mock and the old inventory components once replaced.

**Non-Goals (explicit future work):**

- Expiry dates / lot tracking and vencimiento alerts (C2).
- Canonical ingredient cost and supplier columns (C3 — waits for recipe costing).
- Per-warehouse stock or a storage-location tag (C1).
- Purchases-per-ingredient drawer tab (needs its own endpoint; link out to Compras instead).
- Importar, column-visibility popover, dark theme (already cut in the prototype).

## Decisions

1. **Wire the prototype file, then promote it** — same playbook as `dispatch-board-redesign`:
   port `InventoryDesignView.vue` to the stores in place, verify at `/inventory/design`, then
   point `/inventory` at it and delete `InventoryPanel.vue`, `IngredientDetail.vue`,
   `inventoryDesignMock.ts` and the design route. The old components would survive only as dead
   wrappers; the board's structure (drawer, chips, dual views) doesn't fit them.

2. **`category` is a free-text short field, not a table.** `String(50), nullable` on
   `ingredients`, surfaced as a datalist/Select fed by the distinct categories present. A
   category catalog table would demand its own CRUD screen for marginal value at 12–50 insumos;
   revisit only if pilots ask for renames/merges.

3. **Status derives client-side** exactly as the store already does (`ok`/`low`/`out` from
   quantity vs min); `GET /stock/low` stays unused — one list feeds stats, filters and alerts,
   avoiding double-fetch drift.

4. **Ajuste = recount, not a signed delta.** The prototype's "Ajuste" tab sets the *counted*
   quantity via the `recount` endpoint (its exact semantics), so the modal's third mode reads
   "Recuento" with the counted quantity — matching the backend instead of faking an adjustment
   movement.

5. **Movements need an employee** — keep the current screen's employee Select in the stock
   modal (staff store, active employees of the branch). Auto-deriving the employee from the
   logged-in user is a separate product decision (users ≠ employees for admins) and is not
   taken here.

6. **"Nuevo insumo" composes three real writes**: create ingredient (name, category, unit) →
   optional initial `in` movement → optional threshold. Failures after the first write surface
   partial-success copy ("insumo creado, falta el stock inicial") rather than pretending to be
   atomic — no new composite endpoint for a design change.

7. **CSV export and stats compute from the loaded list** — no new endpoints; the deliveries/runs
   precedent applies (client-side "hoy"-style figures until volume demands server support).

## Risks / Trade-offs

- [Permissions span two modules: creating insumos needs `recipes.manage`, stock actions
  `inventory.adjust`] → gate each control by its own permission; the board is reachable with
  `inventory.read` alone and degrades to read-only.
- [Nuevo insumo is non-atomic (3 writes)] → ordered writes with partial-success messaging and
  the drawer opening on the created insumo so the operator can finish by hand.
- [Free-text categories drift ("Carnes" vs "carnes")] → the filter builds from distinct values
  and the input suggests existing ones; normalization (trim) on save. A catalog table remains
  the escape hatch.
- [Old screen deleted in the same change] → tasks order the swap last, after E2E parity against
  the seeded backend.

## Migration Plan

1. Backend column + migration + schema fields ship first (additive, deployable alone).
2. Frontend port lands behind `/inventory/design` for verification against seeded data.
3. Route swap: `/inventory` → board, `/inventory/design` redirect, old components deleted.
   Rollback = revert the frontend commit; the backend change is additive and safe to keep.

## Open Questions

None blocking. Deferred explicitly: C2 (expiry), C3 (cost), C1 (warehouses/location tag),
purchases-per-ingredient endpoint.
