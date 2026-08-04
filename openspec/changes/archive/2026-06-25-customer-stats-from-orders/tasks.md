## 1. Backend: update customer stats on close

- [x] 1.1 In `modules/orders/infrastructure/repositories.py`: import `CustomerModel`; change the close write so it sets `status`/`closed_at` AND, when `customer_id` is set, issues an atomic `UPDATE customers SET total_spent = total_spent + :total, order_count = order_count + 1, last_purchase_at = :closed_at WHERE id/tenant` in the same commit (a new repo method, e.g. `close_order(tenant_id, order_id, *, customer_id, total, closed_at)`)
- [x] 1.2 In `modules/orders/application/use_cases/manage_orders.py` `close_order`: pass the order's `customer_id` and `total` (and the close timestamp) into that close write, replacing the current `update_order(..., {status, closed_at})` call
- [x] 1.3 In `modules/orders/domain/ports.py`: add/extend the repository port method for the new close signature so strict typing stays sound
- [x] 1.4 Confirm the close still frees the table and remains idempotent (closing again raises a conflict before any stat write); `customer_id` null is a no-op

## 2. Backend tests

- [x] 2.1 Extend `tests/modules/orders/...`: create a customer → create an order with that `customer_id` + an item with a known total → close → assert via `GET /customers/{id}` that `order_count == 1`, `total_spent` equals the order total, and `last_purchase_at` is set
- [x] 2.2 Add an assertion that closing an order with **no** `customer_id` leaves customer stats untouched (and the existing close/inventory tests stay green)
- [x] 2.3 (If reachable cheaply) assert closing the same order twice is rejected and does not double-count

## 3. Backend verification

- [x] 3.1 `poetry run ruff check .` and `poetry run mypy src` clean for the changed modules
- [x] 3.2 `poetry run pytest tests/modules/orders tests/modules/customers` green (no regressions)

## 4. Frontend: surface last purchase

- [x] 4.1 In `front/src/components/customers/CustomerDetail.vue`, show `last_purchase_at` ("Última compra", formatted via `toLocaleDateString('es-CO')`, "—" when null) alongside the existing total_spent / order_count
- [x] 4.2 `pnpm type-check`, `pnpm lint`, `pnpm build`, and `pnpm test:unit` green

## 5. End-to-end verification

- [ ] 5.1 Manual smoke against the running backend: open an order, attach a customer, add items, close it → open Clientes → the customer shows the order in `pedidos`, the total in `Total gastado`, and a `Última compra` date; close a second order for the same customer → counts/total accumulate; close a customer-less order → no customer changes
