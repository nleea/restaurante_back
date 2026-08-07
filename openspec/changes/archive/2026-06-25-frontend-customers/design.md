## Context

The backend `/customers` module is complete but unconsumed, and it has a gap that blocks any
frontend: `CustomerResponse` returns only `person_id` (no name/contact), and there is **no
person-read endpoint** anywhere. So this change has a small backend part (expose person identity on
customer reads) followed by the frontend.

Backend contract (all tenant-scoped — no branch):
- **Customers** (`customers.read` / `customers.manage`): `POST /customers`
  (`{ first_name, last_name, document_number?, phone?, email?, user_id? }` — creates the person
  inline), `GET /customers?active=`, `GET /customers/{id}`, `PATCH /customers/{id}`
  (`{ user_id?, is_active? }`), `DELETE /customers/{id}` (deactivate, returns the customer).
  `CustomerResponse = { id, person_id, user_id, total_spent, order_count, last_purchase_at,
  is_active }` — **today missing name/contact**.
- **Preferences**: `POST /customers/{id}/preferences` (`{ key, value }`),
  `GET /customers/{id}/preferences`, `DELETE /customers/preferences/{prefId}`. `Preference =
  { id, customer_id, key, value }`.
- **Credits (fiado)**: `POST /customers/{id}/credits` (`{ total_amount, reference_id? }`),
  `GET /customers/{id}/credits`, `GET /customers/credits/{creditId}`. `Credit = { id, customer_id,
  total_amount, payment_status: pending|partial|paid, reference_id }`.
- **Credit payments**: `POST /customers/credits/{creditId}/payments`
  (`{ amount, method, employee_id }`), `GET /customers/credits/{creditId}/payments`.
  `CreditPayment = { id, customer_credit_id, amount, method, employee_id }`.
- Money fields (`total_spent`, `total_amount`, `amount`) are server-side `Decimal`, serialized as
  **strings**.

The customers read path today (verified): `GET /customers` → `CustomerService.list_customers` →
`CustomerRepository.list_customers` (a plain `select(CustomerModel)`), mapped in the router via
`CustomerResponse.model_validate(customer, from_attributes=True)` over the domain `Customer`
dataclass. `PersonModel` lives in the identity module, is already imported by the customers
repository (it creates the person inline on customer-create), and `CustomerModel.person_id` FKs
`persons.id` in the same DB/session — so the read path can eagerly load the person.

## Goals / Non-Goals

**Goals:**
- Unblock the frontend by embedding the person's identity (`first_name`, `last_name`,
  `document_number`, `phone`, `email`) in customer reads with the **smallest, lowest-risk backend
  change** that keeps the router mapping intact.
- Build a tenant-scoped customers screen: directory (with name search), preferences, and fiado
  credits with settlement payments — reusing the staff employee picker and money helpers.

**Non-Goals:**
- A general person-management API (only the read embed is added); maintaining order-derived customer
  stats (shown read-only); auto-fiado on order close; POS-cash-linked credit payments;
  realtime/auto-refresh; branch scoping (customers are tenant-wide).

## Decisions

**1. Backend: enrich the read via a `person` relationship + optional entity fields, mapping
unchanged.** Add a `person` relationship on `CustomerModel`, eager-load it (`selectinload`) in
`list_customers`/`get_customer`, add the five identity fields as optional attributes on the `Customer`
read dataclass, and populate them in the `_customer(model)` mapper from `model.person`; on
`create_customer`, populate them from the just-created person. `CustomerResponse` gains the five
optional fields and the router's `model_validate(customer, from_attributes=True)` picks them up — no
router/service signature changes. Alternatives rejected: a separate `GET /persons/{id}` endpoint
(more surface, an extra round-trip per row) and a dedicated read DTO threaded through the service
(wider blast radius). Optional fields on the read entity are a pragmatic read-model enrichment, kept
nullable so existing callers (credit/preference existence checks) are unaffected.

**2. One `CustomersView`, master–detail.** A customer list (master) with an active filter and a
client-side name/document search, and a per-customer detail with three sections: identity (edit/
deactivate), preferences (key/value add/remove), and fiado (credits + settlement payments). On
`< lg` the list drills into a full-screen detail. No branch context — the store loads customers once
for the tenant.

**3. Client-side search; server-side active filter.** The directory search filters the loaded list by
name/document in the client (cheap, instant), while the active/inactive split uses the backend
`active` query param. At pilot scale the full customer list loads fine; pagination is a future add.

**4. Money is string-decimal; the only client arithmetic is credit balances.** `formatCOP` renders
`total_spent`, credit `total_amount`, and payment `amount`; the currency InputNumber captures
amounts sent as `toFixed(2)`. A credit's outstanding balance (`total_amount − Σ payments`) and a
customer's total outstanding (Σ balances of not-`paid` credits) are summed in **integer cents** (as
the cash/procurement screens do); the server's `payment_status` stays authoritative.

**5. Settlement reuses the staff employee picker.** A credit payment's `employee_id` is chosen from
the staff store's active employees (loaded tenant-wide, no branch filter, since customers are
tenant-level). Methods offer the usual presets (cash/card/transfer/Nequi).

**6. Store shape parallels the suppliers/procurement stores.** State: `customers: Customer[]`,
`selectedCustomerId`, `preferences: Preference[]`, `credits: Credit[]`,
`paymentsByCredit: Record<id, CreditPayment[]>`. Getters: `customerName(c)`, `activeCustomers`,
`creditBalance(creditId)`, `customerOutstanding`. Actions (write-through): `loadCustomers()`,
`selectCustomer(id)` (loads preferences + credits), `createCustomer`, `updateCustomer`,
`deactivateCustomer`, `setPreference`, `removePreference`, `registerCredit`, `loadPayments(creditId)`,
`registerCreditPayment` — each refetching the affected collection.

**7. Permission model mirrors existing screens.** Route guard `meta.permission: 'customers.read'`;
within the view, `auth.can('customers.manage')` gates every mutate control. Read-only users see the
directory, preferences, and credits without action affordances.

## Risks / Trade-offs

- **Backend read enrichment loads a person per customer** → mitigated by `selectinload` (one extra
  batched query, not N+1). For the pilot's customer volume this is negligible.
- **Touching the backend breaks the frontend-only pattern** → kept deliberately minimal (read
  enrichment only, nullable fields, mapping unchanged) and covered by an updated API test asserting
  the new fields, so the blast radius is small and verifiable.
- **Client search/total over the loaded list** → if customers are ever paginated, search and any
  totals reflect the loaded page. → No pagination today; flagged for when volume grows.
- **Credit balance vs server payment_status** → the client balance is integer-cents guidance; the
  authoritative `payment_status` from the server is shown alongside and not recomputed.
- **`PATCH /customers/{id}` only accepts `user_id`/`is_active`** (not name/contact) → editing
  identity (name/phone/…) is not supported by the backend update; the detail edit is limited to the
  link/active state, and the create form is where identity is captured. Noted; a person-update API is
  out of scope.

## Migration Plan

Backend change is additive (new optional response fields, a relationship, eager load); no data
migration. Ship the backend first, then the frontend behind existing `customers.read` /
`customers.manage`. Rollback = revert the backend read enrichment and the frontend files/route/nav;
no persisted client state.

## Open Questions

- Should the backend also allow updating person identity (name/phone/…) via `PATCH /customers/{id}`?
  Out of scope here (the update endpoint takes only `user_id`/`is_active`); flagged as a likely
  follow-up so the detail can offer full identity editing.
- Should the directory search hit the backend for large customer bases? Deferred — client search is
  fine at pilot scale.
