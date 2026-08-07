## Why

Customers are referenced (optionally) by orders and delivery, but there is no way to create or manage them, capture preferences, or track store credit (*fiado*) — a very common practice in Colombian neighborhood restaurants. The module exists only as a data layer (`customers`, `customer_preferences`, `customer_credits`, `customer_credit_payments`). Its dependencies (`persons`/`users` from identity, `employees` from staff) are all implemented, so it can be built now and gives orders/delivery a real customer to point at, plus a basic CRM (preferences) and accounts-receivable (credit) capability.

## What Changes

- Add the **application + API layer** for the customers module (hexagonal).
- **Customers**: create a customer by capturing the person inline (name plus optional document, phone, email) and creating the `person` + `customer` together; optionally link a login `user`. List (filter active), get, update, deactivate. `person_id` is unique per tenant.
- **Preferences**: set, list and remove free-form key/value preferences for a customer (lightweight CRM).
- **Store credit (fiado)**: register a credit owed by a customer (amount, optional loose `reference_id` to an order), list a customer's credits, and get one. `payment_status` advances `pending → partial → paid`.
- **Credit payments**: register a payment that settles part/all of a credit (amount, method, employee); recompute the credit's `payment_status` from the sum of payments vs its total. Independent of the POS cash session.
- Stats fields (`total_spent`, `order_count`, `last_purchase_at`) are stored but **not auto-maintained here** — they will be updated by a future orders↔customers integration.
- Enforce **multi-tenant isolation** and **RBAC**: `customers.read` (reads), `customers.manage` (all writes).
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `customers` registration already exist; entities are restructured to the convention.

### Explicitly out of scope (deferred)
- **Orders↔customers stats** — incrementing `total_spent`/`order_count`/`last_purchase_at` when a customer's order closes (future integration).
- **Auto-creating a credit when an order is left on fiado** — a future orders↔customers integration; here credits are registered explicitly.
- **Linking credit payments to the cash drawer** — purchase/credit payments stay independent of `cash` for now.

## Capabilities

### New Capabilities
- `customer-management`: Customers (with inline person creation), preferences, and store credit (fiado) with settlement payments. Tenant-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/customers/`: `domain/ports.py`, `application/use_cases/manage_customers.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; restructure `domain/entities.py` to the convention.
- **Modified**: `src/restaurante/main.py` (include `customers_router`).
- **Cross-module**: the customers repository creates/reads `persons` and validates `users` (identity) and `employees` (staff). No change to those modules' APIs.
- **Reused**: tenant middleware, `shared/database.get_session`, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`), RBAC `require_permission`.
- **APIs**: new `/customers/*` endpoints (customers, preferences, credits, credit payments). No breaking changes.
- **Tests**: new integration suite under `tests/modules/customers/` (sqlite, FK enforcement) — seeds employees directly; persons are created via the API.
