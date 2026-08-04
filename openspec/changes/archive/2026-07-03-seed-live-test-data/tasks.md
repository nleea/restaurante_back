## 1. Scaffolding & shared helpers

- [x] 1.1 Create `backend/scripts/seed_demo.py` with module docstring (usage: `poetry run python -m scripts.seed_demo`), importing `restaurante.shared.models_registry` first
- [x] 1.2 Define status constants (orders=`open`, order_items/order_item_stations=`pending`, dining_tables=`free`, delivery_runs=`preparing`, order_deliveries=`pending`, cash_sessions=`open`, etc.) and demo config constants reusing `DEMO_SLUG`/`DEMO_BRANCH_CODE` from `scripts.seed`
- [x] 1.3 Add a `main()` that opens one `async with SessionFactory() as session:`, calls the existing baseline `seed()` (tenant/branch/admin/RBAC), resolves demo `tenant_id`/`branch_id`, then runs each `seed_<area>` helper in FK order and `commit()` once; `asyncio.run(main())` under `__main__`
- [x] 1.4 Add a small select-or-create utility (lookup by natural key scoped to tenant/branch, else insert) used by all helpers, with `Decimal` used for all Numeric values

## 2. Reference & catalog data

- [x] 2.1 `seed_units_of_measure(session)` — kg, g, L, ml, unit (with base_unit/conversion where relevant), idempotent by abbreviation
- [x] 2.2 `seed_geo(session)` — seed Colombia country + a couple of cities (idempotent), if required by downstream FKs

## 3. Staff & drivers

- [x] 3.1 `seed_persons_and_employees(session, ctx)` — create persons + employees for the demo branch (incl. 2–3 driver employees), idempotent by person natural key
- [x] 3.2 Assign appropriate roles to seeded employees via existing RBAC roles

## 4. Supplies (insumos) & inventory

- [x] 4.1 `seed_supplies(session, ctx)` — create realistic `ingredients` (insumos) each referencing a `unit_of_measure_id`, idempotent by name
- [x] 4.2 `seed_inventory_stock(session, ctx)` — one `inventory_stocks` row per supply for the demo branch with `current_quantity` + `min_stock` (Decimal); optionally seed a few `inventory_movements`

## 5. Purchasing

- [x] 5.1 `seed_suppliers(session, ctx)` — `suppliers` + `supplier_ingredients` (with `reference_price`, `unit_of_measure_id`) for the demo supplies
- [x] 5.2 (Optional) one sample `purchase_request` (+items) in `pending` status to make purchasing screens non-empty

## 6. Menu & recipes (BOM)

- [x] 6.1 `seed_menu(session, ctx)` — `categories`, `products`, `product_prices`, and `product_variants` (a few sellable dishes)
- [x] 6.2 `seed_recipes(session, ctx)` — `recipe_items` linking at least one product variant to seeded supplies with quantities + units

## 7. Customers

- [x] 7.1 `seed_customers(session, ctx)` — a handful of `customers` (idempotent by email/phone) with addresses/neighborhoods for delivery

## 8. Delivery routes (rutas)

- [x] 8.1 `seed_delivery_routes(session, ctx)` — `delivery_routes` with covered zones for the demo branch (idempotent by name)
- [x] 8.2 `seed_route_drivers(session, ctx)` — link driver employees via `delivery_route_drivers` (idempotent by pair)
- [x] 8.3 Create at least one `delivery_run` (status `preparing`) per route

## 9. Orders → payments → cash → finance → deliveries

- [x] 9.1 `seed_dining_tables(session, ctx)` — a few `dining_tables` (status `free`)
- [x] 9.2 `seed_cash_session(session, ctx)` — open `cash_session` for the branch
- [x] 9.3 `seed_orders(session, ctx)` — ≈5–10 `orders` with `order_items` (incl. the recipe-backed variant), `order_payments` against the open cash session
- [x] 9.4 `seed_order_deliveries(session, ctx)` — `order_deliveries` for delivery-channel orders, distributed across delivery states (`pending`/`assigned`/`in_transit`/`delivered`), linked to routes/runs
- [x] 9.5 `seed_finance(session, ctx)` — at least one `expense_category` + `expense`

## 10. Verification & docs

- [x] 10.1 Run `poetry run python -m scripts.seed_demo` against a fresh migrated DB; confirm it commits and prints a per-area summary
- [x] 10.2 Run it a second time; confirm no duplicate rows and no errors (idempotency)
- [x] 10.3 `poetry run ruff check .` and `poetry run mypy src` pass for the new code
- [x] 10.4 Smoke-assert non-empty `ingredients`, `inventory_stocks`, and `delivery_routes` for the demo tenant/branch
- [x] 10.5 Update `backend/CLAUDE.md` command list with the demo load + reset workflow
