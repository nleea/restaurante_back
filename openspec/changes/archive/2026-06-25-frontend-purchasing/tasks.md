## 1. Service layer

- [x] 1.1 Create `front/src/services/purchasing.api.ts` with types `Supplier` and `SupplierIngredient` (`reference_price` typed as `string`, matching backend schemas)
- [x] 1.2 Add supplier calls: `listSuppliers(active?)` (`GET /purchasing/suppliers`), `createSupplier(input)` (`POST /purchasing/suppliers`), `updateSupplier(id, patch)` (`PATCH /purchasing/suppliers/{id}`)
- [x] 1.3 Add catalog calls: `listSupplierIngredients(supplierId)`, `attachIngredient(supplierId, input)`, `detachIngredient(supplierId, ingredientId)`
- [x] 1.4 Add service unit tests in `front/src/services/__tests__/purchasing.api.spec.ts` (URLs, payloads, the `active` param, detach path, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/purchasing.ts` (Pinia options) state: `suppliers`, `selectedSupplierId`, `catalog`, `ingredientIndex`
- [x] 2.2 Add `loadSuppliers()` and `loadDirectory()` (ingredient directory id → { name, unitAbbr } from `listIngredients()` × catalog units, once)
- [x] 2.3 Add `selectSupplier(id)` (loads that supplier's ingredient catalog) and `ingredientLabel(id)` getter with graceful fallback; add `selectedSupplier` and `activeSuppliers` getters
- [x] 2.4 Add supplier mutations `createSupplier` / `updateSupplier` / `deactivateSupplier` (the last calls `updateSupplier(id, { is_active: false })`) — write-through refetch suppliers
- [x] 2.5 Add catalog mutations `attachIngredient` / `detachIngredient` — write-through refetch the selected supplier's catalog
- [x] 2.6 Add store unit tests: suppliers load, directory build + label fallback, supplier create/deactivate write-through, attach/detach write-through, active filter

## 3. Screen, components, routing

- [x] 3.1 Add `/purchasing` route (name `purchasing`, `meta.permission: 'purchasing.read'`) in `front/src/router/index.ts` and a nav link (`Compras`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/PurchasingView.vue` container + `SuppliersPanel.vue` orchestrator: load suppliers + directory, manual refresh, error surface, active-only filter, master list with drill-down
- [x] 3.3 Create the new-supplier dialog (gated by `purchasing.manage`): name + optional tax id / phone / email / address
- [x] 3.4 Create `SupplierDetail.vue`: contact info, edit form and a "Desactivar" action (both via `updateSupplier`), gated by `purchasing.manage`
- [x] 3.5 Create the supplier ingredient catalog in the detail: rows showing ingredient name, unit, and reference price (via `formatCOP`)
- [x] 3.6 Create the attach-ingredient control (gated by `purchasing.manage`): ingredient picker (reuse recipes ingredients, excluding already-attached), unit picker (catalog units), reference price (currency InputNumber); friendly 409 "ese ingrediente ya está registrado"; plus a detach control
- [x] 3.7 Surface API errors with friendly messages (reuse `apiError` helpers); render reference price via `formatCOP`

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create a supplier → edit contact fields → attach an ingredient with a unit + reference price (duplicate shows friendly conflict) → detach → deactivate the supplier; verify a read-only user sees no manage controls
