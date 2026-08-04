# frontend-inventory

## Purpose

The stock-control frontend — the manager-facing client for the backend `/inventory` module, scoped
to the active branch and living on the light office working surface alongside the other back-office
screens. It is a master–detail screen: a **stock list** of the branch's tracked ingredients (on-hand
quantity, unit, reorder threshold) with a low-stock flag and a "solo bajo stock" filter, and a
per-ingredient **detail** that shows on-hand vs reorder point, lets an authorized user set the
threshold, register `in`/`out` movements, and perform a physical recount (counted quantity recorded
as an adjustment), and lists that ingredient's movement history newest-first. Stock rows and
movements carry only `ingredient_id`, so names and units are resolved client-side from
`/recipes/ingredients` crossed with the catalog units, degrading to a short id reference when an
ingredient or unit can't be resolved. Quantities are physical decimals (they can be fractional, e.g.
1.5 kg) rendered with their unit and never as money; the only client-side computation is the
at-or-below-threshold flag. Writes are attributed to an employee via the staff picker. The screen is
reached with `inventory.read`; the threshold, movement, and recount controls are gated by
`inventory.adjust` — this gating is UX, the backend enforces authorization independently. Ingredient
CRUD (recipes module), the orders→recipes→inventory auto-deduction on order close, purchase-order
receiving, valuation/costing, and realtime/auto-refresh are out of scope for this slice.
## Requirements
### Requirement: Inventory service layer

The Inventory API service SHALL expose typed functions covering the branch-scoped `/inventory`
endpoints: list stock (`GET /inventory/branches/{branchId}/stock`); low-stock view
(`GET /inventory/branches/{branchId}/stock/low`); one ingredient's stock
(`GET /inventory/branches/{branchId}/stock/{ingredientId}`); set the reorder threshold
(`PUT /inventory/branches/{branchId}/stock/threshold`); register a movement
(`POST /inventory/branches/{branchId}/movements`); physical recount
(`POST /inventory/branches/{branchId}/recounts`); and movement history
(`GET /inventory/branches/{branchId}/movements/{ingredientId}`). Quantity fields SHALL be carried
as the backend sends them (string-encoded decimals) without lossy reformatting in transport.

#### Scenario: List a branch's stock

- **WHEN** `listStock(branchId)` is called
- **THEN** it GETs `/inventory/branches/{branchId}/stock` and resolves with the array of `Stock`

#### Scenario: Set a reorder threshold

- **WHEN** `setThreshold(branchId, { ingredient_id, min_stock })` is called
- **THEN** it PUTs `/inventory/branches/{branchId}/stock/threshold` and resolves with the updated
  `Stock`

#### Scenario: Register a movement

- **WHEN** `registerMovement(branchId, { ingredient_id, employee_id, type, quantity, reason, ... })`
  is called
- **THEN** it POSTs `/inventory/branches/{branchId}/movements` and resolves with the created
  `Movement`

#### Scenario: Physical recount

- **WHEN** `recount(branchId, { ingredient_id, employee_id, counted_quantity, ... })` is called
- **THEN** it POSTs `/inventory/branches/{branchId}/recounts` and resolves with the recorded
  adjustment result

#### Scenario: List an ingredient's movement history

- **WHEN** `listMovements(branchId, ingredientId)` is called
- **THEN** it GETs `/inventory/branches/{branchId}/movements/{ingredientId}` and resolves with the
  array of `Movement`

### Requirement: Ingredient directory for labels

Because stock and movements carry only `ingredient_id`, the service layer SHALL read the ingredient
directory (`GET /recipes/ingredients`) and the store SHALL resolve each ingredient's name and unit
(unit name/abbreviation from the catalog units), degrading gracefully to a short id reference when
an ingredient or its unit cannot be resolved.

#### Scenario: Resolvable ingredient shows name and unit

- **WHEN** a stock row's `ingredient_id` maps to a known ingredient and unit
- **THEN** the list shows that ingredient's name and unit

#### Scenario: Unresolvable ingredient degrades gracefully

- **WHEN** a stock row's `ingredient_id` cannot be resolved to an ingredient
- **THEN** the list shows a short fallback reference instead of an empty or broken row

### Requirement: Inventory store with branch-scoped state

The Inventory store SHALL hold the active branch's stock rows, the ingredient directory, and the
currently selected ingredient's movement history, and SHALL load stock scoped to the active branch.
Mutations (set threshold, register movement, recount) SHALL be write-through: after a successful
call the store refetches the affected stock and history so server state is shown verbatim.

#### Scenario: Load stock for the active branch

- **WHEN** the store loads inventory for the active branch
- **THEN** `stock` holds that branch's stock rows and the list can render them

#### Scenario: Registering a movement refreshes stock and history

- **WHEN** a movement is registered for an ingredient
- **THEN** the store refetches that branch's stock and the ingredient's movement history so the
  new on-hand and ledger entry appear without a manual reload

#### Scenario: Recount refreshes stock and history

- **WHEN** a physical recount is recorded for an ingredient
- **THEN** the store refetches stock and that ingredient's history so the new on-hand and the
  adjustment entry appear

### Requirement: Stock list with low-stock view

The InventoryView SHALL list the active branch's tracked insumos showing each one's on-hand
quantity, unit, category, reorder threshold state and last-modified time, in a sortable table
(nombre, stock, última modificación) with a card-view toggle; rows at or below their threshold
SHALL be visibly flagged (warn state and row tint), zero-stock rows flagged as agotado (alert
state and tint), and the stock-state filter SHALL narrow the list to en stock, stock bajo or
agotado.

#### Scenario: Low-stock rows are flagged

- **WHEN** an ingredient's on-hand quantity is at or below its reorder threshold
- **THEN** its row is visibly flagged as low stock

#### Scenario: Filter to only low stock

- **WHEN** the user enables the low-stock filter
- **THEN** only rows at or below their threshold are shown

#### Scenario: Sort by stock

- **WHEN** the user sorts by stock ascending
- **THEN** the emptiest insumos appear first

### Requirement: Set reorder threshold

The InventoryView SHALL let an authorized user set an ingredient's reorder threshold (`min_stock`)
to a non-negative value; this action SHALL require the `inventory.adjust` permission. A rejected
value SHALL surface a friendly message.

#### Scenario: Update a threshold

- **WHEN** a user with `inventory.adjust` sets a non-negative reorder threshold for an ingredient
- **THEN** the threshold is saved and the row reflects the new value and low-stock state

### Requirement: Register stock movements and recounts

The InventoryView SHALL let an authorized user register an `in` or `out` movement (quantity, reason,
optional notes) and perform a physical recount (counted quantity → recorded as an adjustment) for an
ingredient, each attributed to an employee; these actions SHALL require the `inventory.adjust`
permission. A stock-out that exceeds on-hand SHALL surface a friendly conflict message rather than a
raw error.

#### Scenario: Register an in movement

- **WHEN** a user with `inventory.adjust` registers an `in` movement with a positive quantity and a
  reason
- **THEN** the movement is recorded and the ingredient's on-hand increases accordingly

#### Scenario: Stock-out beyond on-hand is rejected friendly

- **WHEN** a user registers an `out` movement whose quantity exceeds the ingredient's on-hand
- **THEN** the screen shows a friendly "no hay suficiente existencia" message and no change is made

#### Scenario: Recount records the delta

- **WHEN** a user with `inventory.adjust` submits a physical count for an ingredient
- **THEN** the on-hand becomes the counted value and an adjustment entry appears in its history

### Requirement: Movement history

The InventoryView SHALL show, for a selected ingredient, its movement history newest-first, each
entry showing the movement type, quantity, reason, and when it occurred.

#### Scenario: View an ingredient's history

- **WHEN** a user selects an ingredient
- **THEN** its movements are shown newest-first with type, quantity, and reason

### Requirement: Permission gating and navigation

The Inventory screen SHALL be reachable at `/inventory` only for authenticated users with
`inventory.read`, exposed via a navigation entry; the threshold, movement, and recount controls
SHALL be shown only with `inventory.adjust`. This gating is UX — the backend enforces authorization
independently.

#### Scenario: Read-only inventory user

- **WHEN** the current user has `inventory.read` but not `inventory.adjust`
- **THEN** the stock list and history are visible read-only and no threshold, movement, or recount
  actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `inventory.read` navigates to `/inventory`
- **THEN** the router redirects them to the forbidden view

### Requirement: Inventory board layout

The Inventory screen SHALL be a board with two areas switched by pill tabs — **Insumos** (the
stock table/cards) and **Alertas** (with a live count badge) — and a slide-in detail drawer for
the selected insumo with Detalles, Movimientos and Alertas tabs. Esc and a close control SHALL
dismiss the drawer; on mobile the drawer takes the full width.

#### Scenario: Open and close the drawer

- **WHEN** the user clicks an insumo row or card
- **THEN** the drawer opens on its detail, and Esc or the close control returns to the list

#### Scenario: Alerts tab badge

- **WHEN** N insumos are low or out of stock
- **THEN** the Alertas tab shows N in its badge

### Requirement: Inventory stats and filters

The board SHALL show live counts (total, en stock, stock bajo, agotados — with percentages)
computed from the loaded branch stock, and SHALL filter the list by category, stock state and a
search string (name or category); active filters SHALL render as dismissable chips with a
clear-all control, and filters combine (AND) and apply live.

#### Scenario: Filters combine

- **WHEN** the user picks a category, the "stock bajo" state and types a name fragment
- **THEN** the list shows only insumos matching all three and chips for each active filter

#### Scenario: Stats reflect loaded data

- **WHEN** a movement changes an insumo's stock state
- **THEN** the stat counts update without a page reload

### Requirement: Depletion bar

Every stock figure SHALL render a depletion bar — a thin bar whose fill maps the on-hand
quantity (in table rows, cards, and the drawer's "stock actual vs mínimo" indicator), with the
reorder threshold marked by a notch at the midpoint, colored by state (success / warn / alert).

#### Scenario: Bar reflects state

- **WHEN** an insumo's on-hand is at or below its threshold but not zero
- **THEN** its depletion bar renders in the warn color with the fill left of the notch

### Requirement: Manage insumos from the board

The board SHALL let an authorized user create an insumo through a two-step modal — nombre,
categoría (suggesting existing categories) and unidad first; stock inicial and mínimo second —
composing the real writes in order (create ingredient, optional initial `in` movement, optional
threshold); a failure after the first write SHALL surface partial-success copy naming what
remains. Editing an insumo's nombre/categoría/unidad SHALL reuse the same modal. Creating and
editing SHALL require the `recipes.manage` permission; the stock-related steps additionally
require `inventory.adjust`.

#### Scenario: Create an insumo with initial stock

- **WHEN** a user with `recipes.manage` and `inventory.adjust` completes both steps with an
  initial stock and a minimum
- **THEN** the insumo appears in the list with that stock, threshold and category, and its
  drawer shows the initial movement

#### Scenario: Partial success is named

- **WHEN** the ingredient is created but the initial movement fails
- **THEN** the modal reports that the insumo exists and the stock inicial is pending, and the
  drawer opens on the created insumo

### Requirement: Inventory alerts area

The Alertas area SHALL list Agotados and Stock bajo sections — each row showing the insumo, its
stock vs minimum (with the depletion bar on low rows) and a CTA that opens the stock modal
pre-set to an `in` movement.

#### Scenario: Restock from an alert

- **WHEN** the user clicks the CTA on an agotado row
- **THEN** the stock modal opens for that insumo pre-set to Entrada

### Requirement: Selection and CSV export

The table SHALL support selecting rows (individually and select-all over the filtered list) with
a floating bulk bar, and the board SHALL export the filtered list — or the selection — as a CSV
file generated client-side.

#### Scenario: Export the filtered list

- **WHEN** the user clicks Exportar with filters active
- **THEN** a CSV containing exactly the filtered rows downloads

