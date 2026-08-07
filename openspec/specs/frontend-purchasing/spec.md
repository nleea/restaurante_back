# frontend-purchasing

## Purpose

The supplier master-data frontend — the buyer-facing client for the supplier slice of the backend
`/purchasing` module, living on the light office working surface alongside the other back-office
screens. Suppliers are tenant-scoped (shared across branches), so this is the first screen with no
active-branch context. It is a master–detail screen: a **suppliers list** with an "solo activos"
filter, and a per-supplier **detail** holding the contact info (tax id, phone, email, address) with
an edit form and a deactivate action, plus the supplier's **ingredient catalog** — each row showing
the ingredient name, unit, and reference price, with attach (pick an existing ingredient + unit +
reference price) and detach controls. Because the backend exposes no DELETE, deactivation is a PATCH
that flips `is_active`. Supplier-ingredient rows carry only `ingredient_id`/`unit_of_measure_id`, so
names and units are resolved client-side from `/recipes/ingredients` crossed with the catalog units,
degrading to a short id reference when unresolvable. The reference price is money (COP), rendered with
`formatCOP` and captured with the currency input. The screen is reached with `purchasing.read`; the
supplier create/edit/deactivate and the catalog attach/detach controls are gated by
`purchasing.manage` — this gating is UX, the backend enforces authorization independently. Purchase
requests, approvals, orders, goods receipt, and supplier payments are out of scope for this slice
(a follow-up `frontend-purchasing-orders` change); ingredient CRUD is owned by the recipes module.
## Requirements
### Requirement: Purchasing service layer (suppliers)

The Purchasing API service SHALL expose typed functions covering the supplier slice of
`/purchasing`: list suppliers (`GET /purchasing/suppliers`, optional `active` filter); create a
supplier (`POST /purchasing/suppliers`); update or deactivate a supplier
(`PATCH /purchasing/suppliers/{supplierId}`, the same endpoint patching contact fields and
`is_active`); list a supplier's ingredients (`GET /purchasing/suppliers/{supplierId}/ingredients`);
attach an ingredient (`POST /purchasing/suppliers/{supplierId}/ingredients`); and detach one
(`DELETE /purchasing/suppliers/{supplierId}/ingredients/{ingredientId}`). The `reference_price`
SHALL be carried as the backend sends it (string-encoded decimal) without lossy reformatting in
transport.

#### Scenario: List suppliers with the active filter

- **WHEN** `listSuppliers(true)` is called
- **THEN** it GETs `/purchasing/suppliers` passing `active=true` and resolves with the array of
  `Supplier`

#### Scenario: Create a supplier

- **WHEN** `createSupplier({ name, ... })` is called
- **THEN** it POSTs `/purchasing/suppliers` and resolves with the created `Supplier`

#### Scenario: Deactivate a supplier via patch

- **WHEN** `updateSupplier(id, { is_active: false })` is called
- **THEN** it PATCHes `/purchasing/suppliers/{id}` and resolves with the updated `Supplier`

#### Scenario: Attach an ingredient to a supplier

- **WHEN** `attachIngredient(supplierId, { ingredient_id, reference_price, unit_of_measure_id })` is
  called
- **THEN** it POSTs `/purchasing/suppliers/{supplierId}/ingredients` and resolves with the created
  `SupplierIngredient`

#### Scenario: Detach a supplier ingredient

- **WHEN** `detachIngredient(supplierId, ingredientId)` is called
- **THEN** it DELETEs `/purchasing/suppliers/{supplierId}/ingredients/{ingredientId}`

### Requirement: Purchasing store with supplier state

The Purchasing store SHALL hold the tenant's suppliers, the selected supplier's ingredient catalog,
and an ingredient directory (id → name + unit) resolved from `/recipes/ingredients` crossed with the
catalog units. Mutations (create/update/deactivate supplier, attach/detach ingredient) SHALL be
write-through: after a successful call the store refetches the affected collection so server state is
shown verbatim.

#### Scenario: Load suppliers

- **WHEN** the store loads suppliers
- **THEN** `suppliers` holds the tenant's suppliers and the list can render them

#### Scenario: Creating a supplier refreshes the list

- **WHEN** a supplier is created
- **THEN** the store refetches suppliers so the new supplier appears without a manual reload

#### Scenario: Attaching an ingredient refreshes the catalog

- **WHEN** an ingredient is attached to the selected supplier
- **THEN** the store refetches that supplier's ingredient catalog so the new row appears

### Requirement: Ingredient label resolution

Because supplier-ingredient rows carry only `ingredient_id` and `unit_of_measure_id`, the store SHALL
resolve each row's ingredient name and unit from the recipes ingredient directory and the catalog
units, degrading gracefully to a short id reference when an ingredient or unit cannot be resolved.

#### Scenario: Resolvable row shows ingredient name and unit

- **WHEN** a catalog row's `ingredient_id` maps to a known ingredient and unit
- **THEN** the row shows that ingredient's name and unit

#### Scenario: Unresolvable row degrades gracefully

- **WHEN** a catalog row's `ingredient_id` cannot be resolved to an ingredient
- **THEN** the row shows a short fallback reference instead of an empty or broken row

### Requirement: Manage suppliers

The PurchasingView SHALL list the tenant's suppliers with an active filter and let an authorized user
create a supplier (name plus optional tax id, phone, email, address), edit those fields, and
deactivate a supplier; these mutations SHALL require the `purchasing.manage` permission.

#### Scenario: Create a supplier

- **WHEN** a user with `purchasing.manage` submits the new-supplier form with a name
- **THEN** the supplier is created and appears in the list

#### Scenario: Deactivate a supplier

- **WHEN** a user with `purchasing.manage` deactivates a supplier
- **THEN** the supplier's row reflects an inactive state

#### Scenario: Filter to active suppliers

- **WHEN** the user enables the active-only filter
- **THEN** only active suppliers are shown

### Requirement: Manage supplier ingredient catalog

The PurchasingView SHALL show, for a selected supplier, its ingredient catalog — each row showing the
ingredient name, unit, and reference price — and let an authorized user attach an ingredient (an
existing ingredient with a unit and a non-negative reference price) and detach one; these mutations
SHALL require the `purchasing.manage` permission. A duplicate attach SHALL surface a friendly
message rather than a raw error.

#### Scenario: Attach an ingredient

- **WHEN** a user with `purchasing.manage` attaches an ingredient with a unit and a non-negative
  reference price
- **THEN** the supplier-ingredient is created and appears in the catalog

#### Scenario: Duplicate attach is rejected friendly

- **WHEN** a user attaches an ingredient already registered for that supplier
- **THEN** the screen shows a friendly "ese ingrediente ya está registrado" message and no duplicate
  is created

#### Scenario: Detach an ingredient

- **WHEN** a user with `purchasing.manage` detaches an ingredient from the supplier
- **THEN** the row is removed from the supplier's catalog

### Requirement: Permission gating and navigation

The Purchasing surface SHALL be hosted inside the unified Compras board at `/purchasing` as its
**Proveedores** area tab (not a standalone screen), reachable only for authenticated users with
`purchasing.read` via the single Compras navigation entry; the supplier create/edit/deactivate and
the catalog attach/detach controls SHALL be shown only with `purchasing.manage`. This gating is
UX — the backend enforces authorization independently.

#### Scenario: Suppliers live in the Proveedores tab

- **WHEN** an authenticated user with `purchasing.read` opens the Proveedores area tab of the Compras
  board
- **THEN** the supplier list, contact info, and ingredient catalog are shown, with create/edit/
  deactivate/attach/detach controls gated by `purchasing.manage`

#### Scenario: Read-only purchasing user

- **WHEN** the current user has `purchasing.read` but not `purchasing.manage`
- **THEN** the supplier list, contact info, and catalog are visible read-only and no create, edit,
  deactivate, attach, or detach actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `purchasing.read` navigates to `/purchasing`
- **THEN** the router redirects them to the forbidden view

