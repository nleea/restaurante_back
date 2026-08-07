## 1. Table view-model (occupancy from orders)

- [x] 1.1 Add a helper/computed that maps each `DiningTable` to a view-model: `{ table, openOrder, isOccupied, total }` where `openOrder = orders.orders.find(o => o.dining_table_id === table.id && <open status>)` and `total` is that order's server `total`.
- [x] 1.2 Confirm the open-status predicate against the backend (`status` values returned by `listOrders(status='open')`); centralize it so cards, panel, and delivery list agree.
- [x] 1.3 Add unit tests for the view-model: free table → not occupied/no total; table with an open order → occupied + correct total; branch with no tables → empty.

## 2. Rewire the Salón view to real stores

- [x] 2.1 In `FloorView.vue`, replace `useFloorStore` with `useOrdersStore` + `useBranchStore` + (for the ticket) `useMenuStore`; on mount `branch.ensureLoaded()` then `orders.ensureLoaded(activeBranchId)`, and re-load on `activeBranchId` change (clear selection).
- [x] 2.2 Render the grid from the table view-models; keep the docket/seat/color identity (free → success, occupied → ember). Remove the ticking `now` timer, `heat`, `reserved`, and `section` usages.
- [x] 2.3 Surface the "no active branch" and "user not linked to an employee" empty/disabled states (parity with the removed panel).
- [x] 2.4 Show status summary counts (free/occupied) derived from the view-models.

## 3. Table card + action panel on real data

- [x] 3.1 Rewrite `TableCard.vue` to take a table view-model: mono number, capacity, seat chairs, free/occupied color, and the occupied order total. Drop `dwell`/`heat`/`reservedFor` props.
- [x] 3.2 Rewrite `TablePanel.vue` actions by state: free → "Tomar comanda" (`orders.openOrder(branch, 'dine_in', tableId)`, gated by `orders.create`); occupied → "Ver/editar comanda", "Cobrar", "Cerrar", "Cancelar". Remove reserve/transfer.
- [x] 3.3 Map the 409 on open ("mesa ya está ocupada") and disable opening when there is no resolved employee.
- [x] 3.4 Open the retained `OrderTicket` for view/edit/pay/discount/close/cancel (reuse, do not reimplement); on close/cancel, refresh tables + orders so the table returns to free.

## 4. Register table + delivery order (real API)

- [x] 4.1 Rewrite `RegisterTableModal.vue` to call `orders.createTable(branch, number, capacity)`; keep the editable next-number prefill; remove the `section` field.
- [x] 4.2 Add a single "Nueva orden" dialog with a channel select (Mesa / Para llevar / Domicilio); for `dine_in` also pick a free table; call `orders.openOrder(branch, channel, tableId|null)` and open the ticket. No customer selection (openOrder has no `customer_id`).
- [x] 4.3 Delete the prototype `DeliveryModal.vue` (its fake customer/status flow is replaced by the delivery channel in the "Nueva orden" dialog; driver tracking stays in Delivery/Dispatch).

## 5. Remove Comandas + delete the prototype store

- [x] 5.1 Delete `src/views/OrdersView.vue` and `src/components/orders/OrdersPanel.vue` (keep `components/orders/OrderTicket.vue`).
- [x] 5.2 Router: remove the `/orders` route and add a redirect `/orders` → `/floor`; keep `/floor`.
- [x] 5.3 Sidebar: keep only "Salón" in the "Servicio" group; remove the "Comandas" link.
- [x] 5.4 Delete `src/stores/floor.ts` and `src/stores/__tests__/floor.spec.ts`; delete the now-unused prototype `OrderBuilder.vue` if fully replaced by `OrderTicket`.

## 6. Verify

- [x] 6.1 Parity checklist: every flow the removed `OrdersPanel` supported (open dine_in/takeaway/delivery, list open orders, tables, items, payments, discount, close, cancel, employee/branch gating) is reachable in Salón.
- [x] 6.2 `pnpm type-check`, `pnpm exec vitest run`, and `pnpm lint` all pass; no dangling imports to deleted files.
- [ ] 6.3 `pnpm build` succeeds; manual smoke on `http://demo.localhost:5173/floor` with the API up (open an order, add a variant item, take a payment, close → table frees).
- [x] 6.4 Run `openspec validate --changes replace-comandas-with-salon --strict` and archive readiness check.
