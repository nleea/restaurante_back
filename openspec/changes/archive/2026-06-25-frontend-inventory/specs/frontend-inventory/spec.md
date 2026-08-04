## ADDED Requirements

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

The InventoryView SHALL list the active branch's tracked ingredients showing each one's on-hand
quantity, unit, and reorder threshold, and SHALL flag rows at or below their threshold; a filter
SHALL let the user narrow the list to only low-stock rows.

#### Scenario: Low-stock rows are flagged

- **WHEN** an ingredient's on-hand quantity is at or below its reorder threshold
- **THEN** its row is visibly flagged as low stock

#### Scenario: Filter to only low stock

- **WHEN** the user enables the low-stock filter
- **THEN** only rows at or below their threshold are shown

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
