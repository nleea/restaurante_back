## Context

The `customers` module has 4 ORM tables and domain dataclasses but no functional layer. Customers are optionally referenced by orders/delivery. Dependencies `persons`/`users` (identity) and `employees` (staff) are implemented. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, English identifiers, "small complete system". Colombian context: store credit (*fiado*) and Nequi/Daviplata payment methods are common.

Facts confirmed in code:
- All four tables are tenant-scoped. `customers.person_id` is unique (and FK to global `persons`); `user_id` optional unique (FK to `users`).
- `customers` carries stats (`total_spent`, `order_count`, `last_purchase_at`) defaulted to 0/null.
- `customer_credits`: `total_amount`, `payment_status` (`pending` default), loose `reference_id`. `customer_credit_payments`: `amount`, `method`, `employee_id`, `paid_at` — no `cash_sessions` link.
- `persons` (`PersonModel`, identity) is global (no tenant) and has no owning service/API.
- Permissions `customers.read` / `customers.manage` exist.
- Entities violate the convention (`id`/timestamps required) → restructure.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, API router for: customers (with inline person creation), preferences, store credits, and credit settlement payments.
- Tenant isolation, reference validation, RBAC (read/manage).
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Auto-maintaining customer stats from orders (orders↔customers integration).
- Auto-creating a credit when an order is left on fiado (future integration).
- Linking credit payments to the POS cash drawer.

## Decisions

**1. Mirror the established layout; one `CustomerService`.**
`domain/ports.py` (`CustomersRepository`), `application/use_cases/manage_customers.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`.

**2. Create the person inline with the customer.**
`create_customer` accepts person fields (required name; optional document/phone/email) and the repository inserts a `PersonModel` and a `CustomerModel` in one transaction. Rationale: customers are created ad-hoc at the counter (a walk-in giving a name/phone); requiring a pre-existing `person_id` is impractical because `persons` has no creation API. The customers repo owning person creation is acceptable — `persons` is a shared global table with no other owner. An optional `user_id` is validated against the tenant when provided.

**3. Store credit is an explicit accounts-receivable record; status derived from payments.**
A credit is registered with a positive amount; registering settlement payments recomputes `payment_status` (`paid` if Σ ≥ total, `partial` if 0 < Σ < total, else `pending`) — the same derive-from-sum pattern as purchasing/orders payments. Independent of `cash`. Rationale: fiado is core in the target market; keeping it a simple ledger with derived status is enough now.

**4. Stats are stored but not maintained here.**
`total_spent`/`order_count`/`last_purchase_at` remain at their defaults; a future orders↔customers integration updates them on order close. Rationale: avoid a half-built coupling; the columns exist for when that integration lands.

**5. Validation split: Pydantic for shape, service for business rules.**
Pydantic: required name, positive amounts, required fields. Service: reference existence (user/customer/credit/employee) in tenant, positive-amount rules, payment-status math. Errors reuse `shared/domain/errors`.

**6. RBAC: read vs manage.**
`customers.read` for reads; `customers.manage` for all writes (customers, preferences, credits, payments). Matches the two existing permissions.

## Risks / Trade-offs

- **Inline person creation can create duplicate persons** for the same real individual → accepted; dedup/merge is a later CRM concern. `customers.person_id` uniqueness only prevents two customers sharing one person row.
- **Credit not linked to cash** → settlement cash isn't reflected in the arqueo; intentional for now (a future change can post a cash `in`).
- **Stats not maintained** → reports relying on them are deferred to the orders integration; documented.
- **sqlite vs Postgres** → `Numeric` arithmetic and FK/unique constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all four tables exist in migration `0002`. Autogenerate should be a no-op (verify statically if Postgres unavailable).
2. Deploy is additive — new `/customers` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should creating a customer dedupe by document number when present? (Default: no; allow duplicates, dedup later.)
- Should credit settlement optionally post a cash `in` movement? (Default: out of scope.)
- Should `customers.read` be grantable to delivery/kitchen roles for order context? (Permission already exists; role assignment is a seeding concern, not this change.)
