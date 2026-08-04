## 1. Backend — resolve the current user's employee

- [x] 1.1 Add a repository lookup `find_employee_by_user(tenant_id, user_id)` (returns the employee or `None`) in the staff repository.
- [x] 1.2 Add a `StaffService` method `get_employee_for_user(tenant_id, user_id)` that returns the employee or raises `NotFoundError` (→404).
- [x] 1.3 Add route `GET /staff/employees/me` gated by authentication only (via identity's `get_current_user`, NOT `staff.read`), returning `EmployeeResponse`; `404` when the user is not an employee.
- [x] 1.4 Integration tests: resolves self (`200`); resolves for a user with `orders.*` but no `staff.read`; `404` for a non-employee user; `401` unauthenticated.
- [x] 1.5 Run `ruff`, `mypy`, and `pytest` green.

## 2. Frontend — orders service & store

- [x] 2.1 Add `services/orders.api.ts`: tables (`listTables(branchId)`, `createTable`), orders (`openOrder`, `listOrders({branchId, status?})`, `getOrder`, `setDiscount`, `closeOrder`, `cancelOrder`), items (`listItems`, `addItem`, `updateItemQuantity`, `removeItem`), plus `getMyEmployee()` (`GET /staff/employees/me`). Types for `DiningTable`, `Order`, `OrderItem`.
- [x] 2.2 Add `stores/orders.ts`: `currentEmployee` (resolved once via `getMyEmployee`), tables, orders, items-by-order, and a variant index `variant_id → {productName, variantName, unitPrice}` built from the menu store (products + per-product variants + active-branch prices).
- [x] 2.3 Implement `ensureLoaded({branchId})` (resolve employee + tables + open orders + the variant index), and `openOrder`, refetching the list.
- [x] 2.4 Implement ticket actions with write-through refetch of the order + items: `addItem` (compute `unit_price = branchPrice + variant.extra_price`), `updateQuantity`, `removeItem`, `setDiscount`, `close`, `cancel`.
- [x] 2.5 Unit tests: employee resolution + non-employee path; `unit_price` computation; add/edit/remove/discount/close/cancel forward correctly and refetch; item labeling from the variant index (no raw UUIDs).

## 3. Frontend — comandas screen

- [x] 3.1 Add the `/orders` route (`meta.requiresAuth`, `meta.permission = 'orders.read'`) and a "Comandas" sidebar link gated by `orders.read`.
- [x] 3.2 Build `views/OrdersView.vue` wrapping `AppShell`, master–detail: open-orders list + selected ticket; a tables sub-view and an "Abrir comanda" action.
- [x] 3.3 Tables: list the active branch's tables (number/capacity/status) and a create-table control gated by `orders.create`.
- [x] 3.4 Open-order control (gated `orders.create`): channel selector + table picker (dine-in); disabled with a message when no employee is resolved or no active branch.
- [x] 3.5 Ticket/detail: items list labeled by product/variant + server totals; item picker (product → active variant → quantity) computing and sending `unit_price`; edit quantity; remove item; set discount; close; cancel (reason). Gate each control by its permission.
- [x] 3.6 Empty/blocked states: product without an active variant or without an active-branch price is not addable (with a hint); style with the "El Pase" design system (PrimeIcons `.pi` responsive-class caveat).

## 4. Validation

- [x] 4.1 Frontend: type-check, lint (oxlint + eslint), unit tests, and production build all green.
- [x] 4.2 Verified at the test level: backend integration tests cover /employees/me (self, no-staff.read, 404, 401); frontend unit tests cover employee resolution + non-employee path, unit_price computation from the variant index, item labeling, and write-through refetch for add/discount/cancel; type-check/lint/build green. Live browser walkthrough not run in this pass.
