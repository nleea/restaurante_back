## Context

The backend `/purchasing` module is complete but unconsumed. This change builds only its **supplier
master-data** slice; the procure-to-pay flow (requests → orders → receipt → payments) is a deliberate
follow-up. The supplier contract:

- **Suppliers** (tenant-scoped — no branch): `POST /purchasing/suppliers`
  (`{ name, tax_id?, phone?, email?, address? }`), `GET /purchasing/suppliers?active=`,
  `PATCH /purchasing/suppliers/{id}` (any of the contact fields and/or `is_active`). There is **no**
  GET-by-id and **no** DELETE — deactivation is `PATCH { is_active: false }`.
- **Supplier ingredients**: `POST /purchasing/suppliers/{id}/ingredients`
  (`{ ingredient_id, reference_price, unit_of_measure_id }`),
  `GET /purchasing/suppliers/{id}/ingredients`,
  `DELETE /purchasing/suppliers/{id}/ingredients/{ingredientId}` (204).
- `Supplier = { id, name, tax_id, phone, email, address, is_active }`.
- `SupplierIngredient = { id, supplier_id, ingredient_id, reference_price, unit_of_measure_id,
  is_active }`. `reference_price` is a server-side `Decimal`, serialized as a **string**.
- Perms: `purchasing.read` (reads) / `purchasing.manage` (writes).

Three facts drive the design: (1) **suppliers are tenant-scoped**, so unlike every prior operational
screen this one needs no active-branch context — it's global master data; (2) supplier-ingredient
rows carry only `ingredient_id` + `unit_of_measure_id`, so names/units are resolved client-side,
reusing the `recipes.api.ts` ingredient read and the catalog units the inventory screen already
leaned on; and (3) `reference_price` is **money**, so it renders with `formatCOP` and is captured
with the currency InputNumber the cash/orders screens use. The frontend stack and conventions follow
the existing screens (Vue 3 `<script setup>`, Pinia options stores, PrimeVue + Tailwind, the shared
`@/lib/http` axios instance, mobile-first master–detail as in Staff/Cash/Inventory).

## Goals / Non-Goals

**Goals:**
- A self-sufficient supplier master-data screen: list/create/edit/deactivate suppliers and manage
  each one's ingredient catalog (attach/detach with unit + reference price).
- Resolve readable ingredient/unit labels with graceful fallback, reusing recipes + catalog data.
- Mirror the established store discipline (write-through, `can()` gating) and the master–detail UX.

**Non-Goals:**
- Purchase requests, approvals, orders, goods receipt, and supplier payments (follow-up
  `frontend-purchasing-orders` change).
- Ingredient CRUD (recipes module owns it — read-only directory here).
- Price history/analytics, realtime/auto-refresh, and any branch scoping (suppliers are tenant-wide).

## Decisions

**1. One `PurchasingView`, master–detail, like Staff/Inventory.** A suppliers list (master) with an
active filter, and a per-supplier detail holding the contact form and the ingredient catalog. On
`< lg` the list fills the screen and tapping a supplier drills into a full-screen detail; on `>= lg`
both panes show. Rejected: separate "suppliers" and "catalog" screens — the catalog is owned by a
supplier and belongs in its detail.

**2. No active-branch context.** This is the first screen that is purely tenant-scoped; it does not
read the branch store or scope anything by branch. The store loads suppliers once and the ingredient
directory once. (When the procure-to-pay follow-up lands, requests/orders will reintroduce branch
scope — suppliers themselves stay tenant-wide.)

**3. Deactivate is a PATCH, not a DELETE.** Because the backend exposes no delete, the store's
`deactivateSupplier` calls `updateSupplier(id, { is_active: false })`. Editing contact fields and
deactivating are the same endpoint; the UI presents them as an edit form plus a distinct
"Desactivar" action for clarity, both routed through `updateSupplier`.

**4. Reference price is money; ingredient/unit are resolved labels.** `reference_price` renders via
`formatCOP` and is entered with the currency InputNumber (`mode="currency" currency="COP"
locale="es-CO"`), value stored as a number then sent as a string (`toFixed(2)`), exactly as the cash
screen does. The catalog row's ingredient name comes from the recipes directory and its unit
abbreviation from the catalog units; unresolved rows fall back to a short `#id` ref and an em-dash
unit.

**5. Store shape parallels `inventory.ts`.** State: `suppliers: Supplier[]`, `selectedSupplierId`,
`catalog: SupplierIngredient[]` (the selected supplier's ingredients), `ingredientIndex:
Record<string, { name, unitAbbr }>`. Getters: `selectedSupplier`, `ingredientLabel(id)`,
`activeSuppliers`. Actions (each write-through): `loadSuppliers()`, `loadDirectory()` (ingredients ×
units, once), `selectSupplier(id)` (loads its catalog), `createSupplier`, `updateSupplier`,
`deactivateSupplier`, `attachIngredient`, `detachIngredient`.

**6. Permission model mirrors existing screens.** Route guard `meta.permission: 'purchasing.read'`;
within the view, `auth.can('purchasing.manage')` gates every mutate control (supplier create/edit/
deactivate, catalog attach/detach). Read-only users see suppliers, contact info, and catalog without
action affordances. The backend enforces the same permissions regardless.

## Risks / Trade-offs

- **Label resolution is best-effort** → an ingredient not in the directory (deactivated, or no
  `recipes.read`) shows a short ref. → Mitigation: load the directory + units when the screen opens
  and degrade clearly; the catalog row is still actionable (detach) by id.
- **Duplicate attach returns a conflict** → Mitigation: catch 409 on attach and show "ese
  ingrediente ya está registrado"; keep the form open for correction. The attach dialog can also
  exclude already-attached ingredients from its picker to avoid the error up front.
- **No GET-by-id for a supplier** → the detail renders from the already-loaded list row; after an
  edit the write-through `loadSuppliers()` refresh keeps it current. Acceptable — the list is small.
- **Money vs quantity confusion** → reference price is money (COP, 0 decimals display) while the
  ingredient's unit is physical; the row labels the price with the currency and the unit separately
  so they don't blur.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`purchasing.read` / `purchasing.manage` permissions. Rollback = revert the new files, the router
entry, and the nav link; no persisted client state.

## Open Questions

- Should the supplier list paginate/search as suppliers grow? Deferred — the pilot's supplier count
  is small; a client search box can be added without backend changes.
- Should the attach picker hide ingredients already on the supplier's catalog? Planned as a small UX
  nicety (prevents the duplicate-attach 409); non-blocking and noted in tasks.
