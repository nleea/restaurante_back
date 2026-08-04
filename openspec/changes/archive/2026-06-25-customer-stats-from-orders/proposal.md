## Why

A customer's purchase stats — `total_spent`, `order_count`, `last_purchase_at` — exist on the
customer record and are returned by the API (and shown read-only on the customers screen), but
nothing ever updates them, so they are **always zero**. Orders already carry a (nullable)
`customer_id`, so the data to populate them exists; closing an order is the natural, once-per-order
moment to record the purchase. This wires that gap so the CRM stops lying about "0 pedidos / $0".

## What Changes

- **Backend**: when an order with a linked `customer_id` is **closed**, the system also updates that
  customer's stats in the same atomic operation as the close — increment `order_count` by 1, add the
  order `total` to `total_spent`, and set `last_purchase_at` to the close time. Orders without a
  customer are unaffected. This mirrors the existing close-time side effect (inventory deduction via
  recipes) and the established pattern of the orders repository writing other modules' models in the
  shared session. Exactly-once is guaranteed because a closed order cannot be closed again.
  - `modules/orders/infrastructure/repositories.py`: the close write flips the order status/`closed_at`
    **and**, when `customer_id` is set, atomically increments the customer's stats (importing
    `CustomerModel`, as it already imports inventory/cash models).
  - `modules/orders/application/use_cases/manage_orders.py`: `close_order` passes the order's
    `customer_id` and `total` into that close write.
  - `modules/orders/domain/ports.py`: the repository port gains/extends the close signature.
- **Frontend (small)**: surface the newly-populated `last_purchase_at` ("última compra") in the
  customer detail, alongside the `total_spent` / `order_count` already shown — so the data is visible.
- Tests: a backend test that closes an order with a customer and asserts the customer's
  `order_count`/`total_spent`/`last_purchase_at` updated (and a customer-less order leaves stats
  untouched); the existing close/inventory tests stay green.

Non-goals: recomputing/backfilling stats for orders closed before this change; decrementing stats on
order cancellation or refund (close is the only event that bumps them); a "lifetime value / loyalty"
layer; and any new endpoint (stats are read through the existing customer reads). Auto-creating a
fiado credit on an unpaid order and linking credit payments to cash remain separate concerns.

## Capabilities

### Modified Capabilities
- `order-management`: closing an order SHALL, when the order has a linked customer, update that
  customer's purchase stats (`order_count`, `total_spent`, `last_purchase_at`) atomically with the
  close and exactly once — a new close-time side effect alongside the existing inventory deduction.
- `customer-management`: the Purpose note listing "maintaining customer stats from orders" as out of
  scope is retired — those stats are now maintained by the order-close flow (a prose correction; no
  requirement-level change to customer reads, which already return the stats).

## Impact

- **Backend code**: `modules/orders/infrastructure/repositories.py` (close write + `CustomerModel`
  import), `modules/orders/application/use_cases/manage_orders.py` (`close_order` passes
  customer/total), `modules/orders/domain/ports.py` (port signature); plus
  `tests/modules/orders/...` (assert stats update on close).
- **Frontend code**: `front/src/components/customers/CustomerDetail.vue` — show `last_purchase_at`.
  No store/service change (the field is already on `Customer`).
- **Backend behavior change (intentional)**: closing an order with a customer now writes to that
  customer's row in the same transaction. Customer-less orders are unchanged. No new endpoint.
- **Permissions/RBAC**: unchanged — this is an internal cross-module write triggered by the existing
  `orders.write`-gated close, not a new user action.
- **Dependencies**: none.
