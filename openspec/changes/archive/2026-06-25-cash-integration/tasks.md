## 1. Backend: purchasing → cash

- [x] 1.1 In `modules/purchasing/infrastructure/repositories.py`: import `CashSessionModel`/`CashMovementModel`; add an open-session lookup (`get_open_cash_session(tenant_id, branch_id)`) mirroring the orders repo
- [x] 1.2 Extend the purchasing payment write so that, when a resolved cash posting is supplied, it adds a `CashMovementModel(type="out", concept="purchase_payment", reference_id=order_id, amount, method, branch_id, cash_session_id)` atomically with the `PurchasePaymentModel`
- [x] 1.3 In `manage_purchasing.py` `register_payment`: when `method == "cash"`, look up the open session for the order's `branch_id`, raise `ConflictError` if none, and pass the branch + session to the repo; non-cash writes no movement
- [x] 1.4 Update `tests/modules/purchasing/...`: cash payment records a matching `out`/`purchase_payment` movement on the open session and is rejected (409) when no session is open; a non-cash payment writes no movement

## 2. Backend: fiado → cash

- [x] 2.1 In `modules/customers/infrastructure/repositories.py`: import the cash models; add `get_open_cash_session(tenant_id, branch_id)` and an `employee_branch(tenant_id, employee_id)` lookup (`EmployeeModel.branch_id`)
- [x] 2.2 Extend the credit-payment write so that, when a resolved cash posting is supplied, it adds a `CashMovementModel(type="in", concept="credit_payment", reference_id=credit_id, amount, method, branch_id, cash_session_id)` atomically with the `CustomerCreditPaymentModel`
- [x] 2.3 In `manage_customers.py` `register_credit_payment`: when `method == "cash"`, resolve the paying employee's branch, look up its open session, raise `ConflictError` if none, and pass branch + session to the repo; non-cash writes no movement
- [x] 2.4 Update `tests/modules/customers/...`: cash settlement records a matching `in`/`credit_payment` movement on the open session and is rejected (409) when no session is open; a non-cash settlement writes no movement

## 3. Backend verification

- [x] 3.1 `poetry run ruff check .` and `poetry run mypy src` clean for the changed modules
- [x] 3.2 `poetry run pytest tests/modules/purchasing tests/modules/customers tests/modules/cash tests/modules/orders` green (no regressions in the cash/orders integration)

## 4. Frontend: legibility

- [x] 4.1 Map the new 409 to a clear "No hay una caja abierta para registrar el pago en efectivo." in the procurement payment dialog (`components/procurement/OrdersArea.vue`) and the customers settlement dialog (`components/customers/CustomerDetail.vue`)
- [x] 4.2 Add a concept-label helper (`sale`→"Venta", `purchase_payment`→"Pago a proveedor", `credit_payment`→"Abono fiado", fallback to the raw concept) and use it in the cash ledger (`components/cash/ActiveDrawer.vue`) and the history detail (`components/cash/SessionHistory.vue`)
- [x] 4.3 Add/extend a small unit test for the concept-label helper

## 5. Frontend verification

- [x] 5.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 5.2 `pnpm test:unit` green

## 6. End-to-end verification

- [ ] 6.1 Manual smoke against the running backend: open a cash session → register a purchase cash payment (drawer expected cash falls; movement shows "Pago a proveedor") → register a fiado cash settlement (drawer expected cash rises; movement shows "Abono fiado") → attempt a cash payment with no open session (friendly 409) → confirm a card payment writes no cash movement; close the session and verify the arqueo includes these movements
