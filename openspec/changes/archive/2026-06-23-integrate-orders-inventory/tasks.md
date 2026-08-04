## 1. Domain / ports

- [x] 1.1 Extend `orders/domain/ports.py` (`OrdersRepository`) with `consume_inventory_for_order(tenant_id, order_id) -> None` (recipe-driven, idempotent, negative-allowed inventory deduction for a closed/closing order).

## 2. Infrastructure — repository

- [x] 2.1 In `orders/infrastructure/repositories.py`, import `RecipeItemModel` (recipes) and `InventoryStockModel` + `InventoryMovementModel` (inventory).
- [x] 2.2 Implement `consume_inventory_for_order`:
  - Idempotency: if any `inventory_movements` with `reference_id = order_id` AND `reason = 'sale'` exist, return (no-op).
  - Load the order (for `branch_id`, `employee_id`) and its non-cancelled items.
  - For each item, load `recipe_items` for its `product_variant_id`; for each recipe line compute `consumed = recipe_line.quantity * item.quantity`.
  - Upsert the `(ingredient_id, branch_id)` stock row (create with negative on-hand if missing; else decrement `current_quantity` by `consumed`, allowing negative).
  - Insert an `InventoryMovementModel` (`type='out'`, `reason='sale'`, `quantity=consumed`, `employee_id=order.employee_id`, `reference_id=order_id`, ingredient/branch/tenant).
  - Commit once for the whole deduction.

## 3. Application — service

- [x] 3.1 In `OrderService.close_order` (`orders/application/use_cases/manage_orders.py`): after guarding the order is open, call `repo.consume_inventory_for_order(tenant_id, order_id)` before/at the close, then update status `closed` + `closed_at` and free the table (keep existing behavior). Ensure deduction runs exactly once per close.

## 4. Verification

- [x] 4.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 4.2 Extend `tests/modules/orders/` (new module, e.g. `test_orders_inventory.py`, sqlite + FK on) covering: closing deducts `recipe_qty × item_qty` as an `out`/`sale` movement and decrements stock; insufficient stock still closes and goes negative; variant without a recipe consumes nothing; cancelled items are skipped; idempotency (a closed order is not re-deducted / cannot re-close). Seed variant + recipe (ingredient + unit) + initial stock directly.
- [x] 4.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 4.4 Update `docs/ESTADO_PROYECTO.md` (orders→inventory deduction done; BOM→stock loop closed).
