## 1. Backend — schema

- [x] 1.1 Add `orders.cash_session_id` (nullable `Uuid`, FK → `cash_sessions.id` `ondelete=SET NULL`, indexed) to `OrderModel`, domain `Order`, and repository mapping
- [x] 1.2 Alembic migration `0019_orders_cash_session` (add column + index); run up/down on Postgres

## 2. Backend — gate + stamp (the choke point)

- [x] 2.1 Add `CashClosedError` to `shared/domain/errors.py` and map it to HTTP 409 in `shared/api/errors.py`
- [x] 2.2 Inject the cash open-session resolver (`get_open_session`) into `OrderService` (new `orders → cash` edge at creation, mirroring the payment path)
- [x] 2.3 In `OrderService.open_order`: resolve the branch's open session; raise `CashClosedError` when none; otherwise stamp `order.cash_session_id`
- [x] 2.4 Verify all channels funnel through `open_order` (salón/comanda, storefront `manage_storefront.create_order`, delivery-origin) — no bypass path creates an order without the gate

## 3. Backend — live boards scoped to the open session

- [x] 3.1 Delivery: scope `list_deliveries` to the branch's open session (join order's `cash_session_id`); exclude null/closed-session deliveries
- [x] 3.2 Kitchen: scope the kitchen board listing to the branch's open session (via the order)
- [x] 3.3 Salón: scope the active-orders listing to the branch's open session
- [x] 3.4 Confirm null `cash_session_id` rows never match any live query (no backfill)

## 4. Backend — tests

- [x] 4.1 `open_order` stamps the open session; rejects with `CashClosedError` (409) when none — covering salón + storefront paths
- [x] 4.2 Deliveries list returns only the open session's deliveries; excludes closed-session and null; empty when no open session
- [x] 4.3 Kitchen + salón listings scoped the same way
- [x] 4.4 Storefront order intake returns 409 when the caja is closed and 201 when open

## 5. Frontend

- [x] 5.1 Dispatch store/view: render the scoped deliveries list; add a "caja cerrada" empty state distinct from "no deliveries yet"
- [x] 5.2 Storefront + salón: detect the 409 closed-caja rejection and show a "caja cerrada" message (basic copy; opening-hours enrichment is a later change)
- [x] 5.3 Frontend tests: dispatch shows closed state on empty/closed; order attempt surfaces the closed-caja message

## 6. Validation

- [x] 6.1 Backend tests + ruff + mypy; alembic up/down on Postgres
- [x] 6.2 Frontend type-check, unit tests, lint, build
- [x] 6.3 `openspec validate cash-session-operating-shift --strict` passes
