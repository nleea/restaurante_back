## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` to the convention (business fields first; `id`, `registered_at`, `paid_at`, stats defaulted) for `Customer`, `CustomerPreference`, `CustomerCredit`, `CustomerCreditPayment`.
- [x] 1.2 Create `domain/ports.py` with a `CustomersRepository` `Protocol`: existence checks (user/employee); `create_customer(person_fields, customer)` (creates person + customer atomically); customer get/list(filter active)/update; preference set/list/delete; credit create/get/list-by-customer/update; credit-payment create/list; `credit_payments_total(credit_id)`. Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyCustomersRepository(session)` implementing the port, filtering by `tenant_id`. Import identity (`PersonModel`, `UserModel`) and staff (`EmployeeModel`) for person creation + reference checks.
- [x] 2.2 Implement existence helpers (`user_exists`, `employee_exists`) + ORM→entity mappers.
- [x] 2.3 `create_customer`: insert `PersonModel` (name/document/phone/email) then `CustomerModel` (person_id, optional user_id), commit once → catch unique violation → `ConflictError`. Customer get/list(filter active)/update.
- [x] 2.4 Preferences (set/list/delete). Credits (create/get/list by customer/update). Credit payments (create; list; `credit_payments_total`).

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_customers.py` with `CustomerService(repo)`, credit status constants (`pending/partial/paid`), and guards `_require_customer`, `_require_credit`, `_require_employee`.
- [x] 3.2 Customers: create (require name; validate optional user in tenant), list (filter active), get, update, deactivate.
- [x] 3.3 Preferences: set (validate customer), list, delete.
- [x] 3.4 Credits: register (validate customer; positive amount → else `ValidationError`), list by customer, get.
- [x] 3.5 Credit payments: register (validate credit + employee; positive amount; recompute credit `payment_status` from `credit_payments_total` vs `total_amount`), list.

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_customer_service`, `CustomerServiceDep`).
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: create-customer (name required + optional document/phone/email/user_id); update-customer; set-preference (key/value); create-credit (amount>0, optional reference_id); credit-payment (amount>0, method, employee); responses for customer, preference, credit, credit-payment.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/customers", tags=["customers"])`. Permission deps: read=`customers.read`, manage=`customers.manage`. Endpoints: customers create/list/get/update/deactivate; preferences set/list/delete; credits create/list-by-customer/get; credit payments create/list.
- [x] 4.4 Register `customers_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Write integration tests under `tests/modules/customers/` (sqlite, FK enforcement on) covering: tenant isolation; create customer (person created) + unknown-user 404 + list/get + deactivate; preferences set/list/delete; credit register + non-positive 422 + unknown-customer 404; credit payment partial→paid + non-positive 422; RBAC 403 for read/manage. Seed employees directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/customers` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (customers implemented).
