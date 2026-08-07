## 1. Service layer

- [x] 1.1 Extend `front/src/services/purchasing.api.ts` with types `PurchaseRequest`, `PurchaseRequestItem`, `PurchaseOrder`, `PurchaseOrderItem`, `PurchasePayment` (money/quantity fields typed as `string`)
- [x] 1.2 Add request calls: `createRequest(input)`, `listRequests(status?)`, `listRequestItems(id)`, `approveRequest(id, { employee_id })`, `rejectRequest(id, { employee_id })`
- [x] 1.3 Add order calls: `createOrder(input)`, `listOrders(status?)`, `listOrderItems(id)`, `receiveOrder(id, { received_by_employee_id, items })`
- [x] 1.4 Add payment calls: `registerPayment(orderId, { amount, method, employee_id })`, `listPayments(orderId)`
- [x] 1.5 Add service unit tests in `front/src/services/__tests__/purchasing.flow.api.spec.ts` (URLs, payloads, status_filter, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/procurement.ts` (Pinia options) state: `requests`, `requestItems`, `orders`, `orderItems`, `payments`, `selectedRequestId`, `selectedOrderId`
- [x] 2.2 Add `loadRequests(status?)` / `loadOrders(status?)` and `branchRequests` / `branchOrders` getters filtering by the active branch's `branch_id`
- [x] 2.3 Add `loadRequestItems(id)`, `loadOrderItems(id)`, `loadPayments(orderId)`, `selectRequest(id)`, `selectOrder(id)`
- [x] 2.4 Add request mutations `createRequest` / `approveRequest` / `rejectRequest` (write-through refetch requests)
- [x] 2.5 Add order mutations `createOrder` (refetch orders) and `receiveOrder` (refetch the order + its items); add `registerPayment` (refetch the order + its payments)
- [x] 2.6 Add `outstandingBalance(orderId)` getter (`total − Σ payments` in integer cents) and `receiptProgress(item)` helper
- [x] 2.7 Add store unit tests: branch filtering, approve/create/receive/pay write-through refetch, outstanding-balance derivation, received progress

## 3. Screen, components, routing

- [x] 3.1 Add `/procurement` route (name `procurement`, `meta.permission: 'purchasing.read'`) in `front/src/router/index.ts` and a nav link (`Abastecimiento`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/ProcurementView.vue` container + `ProcurementPanel.vue` orchestrator: active-branch guard, load (requests/orders + ensure suppliers/ingredients/units/staff loaded), area switch (Solicitudes / Órdenes), refresh, error surface
- [x] 3.3 Create the Requests area: list by status (master) + request detail (line items with ingredient/quantity/unit) with approve/reject actions gated by `purchasing.approve`, shown only when `pending`
- [x] 3.4 Create the new-request dialog (gated by `purchasing.manage`): requesting employee, optional reason, and a repeatable line editor (ingredient + quantity + unit); block empty/non-positive
- [x] 3.5 Create the Orders area: list by status (master) + order detail (supplier, status, payment status, total, items with received-vs-ordered progress)
- [x] 3.6 Create the new-order dialog (gated by `purchasing.manage`): pick an approved request → supplier + per-line ordered quantity and unit price (pre-fill quantity from the request and price from the supplier's reference where available)
- [x] 3.7 Create the receive control (gated by `purchasing.manage`): per-item received quantity + employee; and the register-payment control (amount via currency input, method, employee) showing the outstanding balance; friendly 409/422 messages
- [x] 3.8 Render money via `formatCOP` and quantities via `formatQuantity`; resolve ingredient/supplier/employee labels from the existing stores; surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create a request → approve → create an order (supplier + prices) → receive items (stock rises in inventory; status → partially/received) → register a payment (payment_status → partial/paid, balance falls); verify read-only and approve-only permission gating
