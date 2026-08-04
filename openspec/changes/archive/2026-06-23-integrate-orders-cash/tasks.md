## 1. Domain / ports

- [x] 1.1 Extend `orders/domain/ports.py` (`OrdersRepository`) with: `get_open_cash_session(tenant_id, branch_id) -> CashSession | None`; `register_payment(payment: OrderPayment) -> OrderPayment` (writes the order payment + the `sale` cash movement atomically); `list_payments(tenant_id, order_id) -> list[OrderPayment]`.
- [x] 1.2 Confirm the `OrderPayment` entity has the needed fields (tenant/branch/order/cash_session/amount/method/diner_reference/employee). No change expected.

## 2. Infrastructure — repository

- [x] 2.1 In `orders/infrastructure/repositories.py`, import `CashSessionModel` and `CashMovementModel` from the cash module; add a `_cash_session` mapper (or reuse a minimal projection) returning the `CashSession` entity.
- [x] 2.2 Implement `get_open_cash_session` (query `CashSessionModel` by tenant + branch + status `open`).
- [x] 2.3 Implement `register_payment`: insert `OrderPaymentModel` and a derived `CashMovementModel` (`type='in'`, `concept='sale'`, `method`, `amount`, `reference_id=order_id`, same session/branch/tenant), then `commit()` once; refresh and return the payment entity.
- [x] 2.4 Implement `list_payments` (by tenant + order, ordered by creation).

## 3. Application — service

- [x] 3.1 Create `orders/application/use_cases/manage_payments.py` with `PaymentService(repo)`; reuse guards for order existence/open and employee existence (raise `NotFoundError`/`ConflictError`).
- [x] 3.2 `register_payment`: require order exists and is `open`; require employee in tenant; reject non-positive amount (`ValidationError`); resolve the branch's open cash session (missing → `ConflictError`); build the `OrderPayment` and delegate to `repo.register_payment`.
- [x] 3.3 `list_payments`: require order exists; return `repo.list_payments`.

## 4. API layer

- [x] 4.1 Add payment schemas to `orders/infrastructure/api/schemas.py`: `RegisterPaymentRequest` (`amount` `gt=0`, `method` non-empty, `employee_id`, optional `diner_reference`) and `OrderPaymentResponse`.
- [x] 4.2 Add a `PaymentServiceDep` to `orders/infrastructure/api/deps.py` (build `PaymentService` over the orders repo).
- [x] 4.3 Add endpoints to `orders/infrastructure/api/router.py`: `POST /orders/{order_id}/payments` (`orders.pay`) and `GET /orders/{order_id}/payments` (`orders.read`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Extend `tests/modules/orders/` with a payments test module covering: charge with open session writes both order payment + `sale` cash movement; cash payment is reflected in the closed session's `expected_amount`; non-cash payment excluded from drawer count; reject charge with no open session (409); reject charging a closed/cancelled order (409); non-positive amount 422; unknown employee 404; list payments; RBAC 403 for `orders.pay`.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Update `docs/ESTADO_PROYECTO.md` (orders→cash payment integration done; orders no longer "core only" for charging).
