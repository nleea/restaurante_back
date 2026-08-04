## Why

This is the payoff of the whole BOM design: until now, selling a dish never touched real stock. `recipes` defines what ingredients each product variant consumes, `inventory` tracks on-hand per branch, and `orders` records what was sold — but nothing connects sale to consumption. This change closes that loop: **when an order is closed, the system deducts each item's ingredients from inventory via its recipe**, so on-hand reflects reality and (later) costing/margin become computable. It is the reason `recipes` and `inventory` were built. With `orders` (core + cobro) and both modules live, the integration can be implemented now.

## What Changes

- **On closing an order**, the system deducts inventory: for every non-cancelled order item, it looks up the item's product-variant recipe (BOM) and, for each ingredient line, records an inventory `out` movement of `recipe_quantity × item_quantity` at the order's branch, reason `sale`, `reference_id = order_id`, attributed to the order's employee. Stock is decremented in the same transaction as the close.
- **Deduction is non-blocking and may drive stock negative** — the sale already happened; closing must not fail because stock is short. Negative on-hand is a signal that a physical recount is due (the recount/adjustment flow already exists in inventory).
- **Idempotent**: if an order already has `sale` movements (already consumed), closing again does not double-deduct (closing is one-shot anyway — a closed order cannot be re-closed).
- **Variants without a recipe consume nothing** (no BOM → no deduction), so the close still succeeds.
- No new endpoints — deduction is a side effect of the existing `POST /orders/{id}/close` (permission `orders.update`).

### Explicitly out of scope (deferred)
- **Unit conversion** between a recipe line's unit and the ingredient's stock unit — assumed equal (the recipes module already deferred conversions). Documented as a limitation.
- **Costing / margin** computation from consumed ingredients — needs ingredient costs from `purchasing`; a later change.
- **Reversing consumption** when a closed order is later corrected — not modeled (orders cannot be reopened).

## Capabilities

### New Capabilities
<!-- None — this extends an existing capability. -->

### Modified Capabilities
- `order-management`: closing an order now deducts ingredients from inventory via the product-variant recipes (BOM), recording `sale` inventory movements.

## Impact

- **Modified code**: extend `orders/domain/ports.py` and `orders/infrastructure/repositories.py` with a recipe-aware inventory-consumption method; call it from `OrderService.close_order` (`orders/application/use_cases/manage_orders.py`).
- **Cross-module reads/writes**: the orders repository reads `recipe_items` (recipes) and `ingredients` indirectly, and writes `inventory_movements` + updates `inventory_stocks` (inventory) — both in addition to its own tables. No change to recipes' or inventory's public APIs.
- **Reused**: existing `inventory_stocks`/`inventory_movements` model and the negative-allowed `apply_movement` semantics (the inventory **repository** applies a delta without the service-level over-draw guard), `recipe_items` listing, `shared/domain/errors`.
- **Behavioral change**: `POST /orders/{id}/close` now also produces inventory movements. No API signature change; no breaking change to other modules.
- **Tests**: extend `tests/modules/orders/` — closing deducts per recipe × quantity, allows negative, skips no-recipe variants, ignores cancelled items, is idempotent.
