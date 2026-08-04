## Why

Inventario now has a board — stats, combined filters with chips, a sortable table with the
depletion bar, a detail drawer and an alerts area — that made the back-office view legible at a
glance. Compras is still two thin master–detail screens (`/purchasing` = Proveedores,
`/procurement` = solicitudes/órdenes/recepción/pagos) with no stats, no filters, no progress
signal and no drawer. The procurement store already computes the two figures that make a board
worth it — **receipt progress** (received vs ordered, the depletion-bar analog) and **outstanding
balance** (por pagar) — but nothing surfaces them. This change adapts the Inventario board design
to Compras so buyers can see, at a glance, what is on order, what is half-received and what is
still owed.

## What Changes

- **One Compras board** at `/purchasing`, order-centric, in the El Pase board language, replacing
  the current `PurchasingView`/`ProcurementView` split. Purchase orders are the spine; **Órdenes**,
  **Solicitudes** and **Proveedores** are pill area tabs (mirroring Inventario's Insumos/Alertas).
- **Stats row:** live counts of orders by status (Creada / Parcial / Recibida) plus total
  **por pagar** (Σ outstanding balance), computed client-side from the loaded branch orders.
- **Toolbar + chips:** search (proveedor / nº orden), supplier filter, status filter, sort, and a
  list/cards view toggle; active filters render as dismissable chips with clear-all; filters
  combine (AND) and apply live.
- **Receipt-progress bar** (the depletion-bar analog): every order row/card and the drawer render a
  thin bar mapping `received/ordered`, colored by state (creada / parcial→warn / recibida→success),
  fed by the existing `receiptProgress` derivation.
- **Detail drawer** for the selected order with **Detalles / Ítems / Pagos** tabs (mirroring
  Detalles/Movimientos/Alertas): item lines with per-line received quantity, and the payments
  timeline with the outstanding figure.
- **Action modals** reusing the staff employee `Select`: **Recibir mercancía** (per-item counted
  quantities → `receiveItems`, which already posts inventory `in` movements reason `purchase`),
  **Registrar pago** (amount/method → `registerPayment`), and **Nueva solicitud / Nueva orden**
  (create request → approve → order, the flow that already exists).
- **Solicitudes tab:** request list with pending/approved/rejected buckets, approve/reject
  (gated `purchasing.approve`) and "crear orden desde aprobada".
- **Proveedores tab:** the existing suppliers UI (`SuppliersPanel`/`SupplierDetail`) folded in as
  an area tab — no behavioral change to supplier CRUD or the ingredient catalog.
- **Alerts area:** órdenes con saldo pendiente y órdenes parcialmente recibidas, each with a quick
  action (Registrar pago / Recibir).
- **CSV export** of the current (filtered) order list, computed client-side.
- **Route cleanup:** `/purchasing` renders the board; `/procurement` redirects to it;
  `ProcurementView.vue` + `ProcurementPanel.vue` are retired once parity is verified.

### Explicit future work (out of scope, decided in exploration)

- **No backend changes** — every field the board needs (order status, ordered/received per item,
  totals, payments, supplier) is already exposed; stats/filters/export stay client-side.
- **Server-side filtering/pagination** — only if order volume outgrows the client filter.
- **Costing / margin and supplier-performance metrics** — needs canonical ingredient cost (the
  same dependency Inventario deferred as C3); the board reserves no column for it yet.
- **Editing or cancelling a placed/received order** — not modeled today; unchanged here.

## Capabilities

### New Capabilities

None — both affected frontend capabilities already exist.

### Modified Capabilities

- `frontend-purchasing-orders`: the procurement screen becomes the order-centric Compras board —
  stats, combined filters with chips, sortable table + cards with the receipt-progress bar and
  status/payment pills, detail drawer (Detalles/Ítems/Pagos), Recibir and Registrar pago modals,
  Solicitudes area with approve/reject and order creation, alerts area, CSV export — served at
  `/purchasing`. Existing gates (`purchasing.read`/`manage`/`approve`) and the branch-scoped store
  derivations (`receiptProgress`, `outstandingBalance`) are preserved.
- `frontend-purchasing`: `PurchasingView` becomes the host of the unified Compras board and the
  suppliers management moves into a **Proveedores** area tab; the standalone `/procurement` route
  is retired (redirect). Supplier CRUD and ingredient-catalog behavior are unchanged.

## Impact

- **Frontend:** `views/PurchasingView.vue` (becomes the board host), `views/ProcurementView.vue`
  (retired → redirect), new `components/purchasing/*` board pieces (or an extended
  `ProcurementPanel`), `components/purchasing/SuppliersPanel.vue`/`SupplierDetail.vue` (embedded as
  the Proveedores tab), `stores/procurement.ts` + `stores/purchasing.ts` (board helpers: stats,
  distinct-supplier/status getters), `router/index.ts` (route swap + redirect), unit tests.
- **Backend:** none — no new endpoints, schemas or migrations.
- **No breaking API changes.**
