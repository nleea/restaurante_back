## Why

The backend `/customers` module — customer records (with an inline person), free-form preferences
(lightweight CRM), and store credit (*fiado*) with settlement payments — has no frontend, so the
restaurant can't keep a customer directory, note preferences, or track who owes on credit. It also
gives orders/delivery a real customer to reference. A blocker must be cleared first: today
`CustomerResponse` returns only `person_id` (no name/contact), and there is **no person-read
endpoint**, so a customer list would be nameless. This change adds the missing read data to the
backend and then builds the frontend on top.

## What Changes

- **Backend (enabling)**: embed the person's identity on customer reads — add `first_name`,
  `last_name`, `document_number`, `phone`, and `email` to `CustomerResponse`, populated via a
  `person` relationship on the customer read path (list + get + create response). No new endpoint;
  the existing create already captures these fields. This is the minimal change that makes a usable
  customer directory possible.
- Add a **Customers service layer** (`customers.api.ts`) over `/customers`: customers
  (`POST /`, `GET /?active=`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` — deactivate), preferences
  (`POST /{id}/preferences`, `GET /{id}/preferences`, `DELETE /preferences/{prefId}`), credits
  (`POST /{id}/credits`, `GET /{id}/credits`, `GET /credits/{creditId}`), and credit payments
  (`POST /credits/{creditId}/payments`, `GET /credits/{creditId}/payments`).
- Add a **Customers store** (`customers.ts`): the tenant's customers (now with name/contact), the
  selected customer's preferences and credits, a credit's payments, and client-side derivations —
  each credit's outstanding balance (`total_amount − Σ payments`) and the customer's total
  outstanding across pending/partial credits. Money is carried as string-decimals.
- Add the **CustomersView** screen, mobile-first master–detail:
  - **Customer list** (master): name, document/phone, active badge, with an "solo activos" filter and
    a client-side name/document search. Read needs `customers.read`.
  - **Customer detail**: identity (name, document, phone, email) read-only with a deactivate/
    reactivate action (the backend update accepts only active state + user link, so identity is set
    at creation);
    **preferences** (key/value add/remove); and **fiado** — register a credit, list credits with
    their payment status and balance, and **register a settlement payment** (amount, method,
    employee) showing the outstanding balance. All mutations gated by `customers.manage`.
- Add the **route + nav entry** (`/customers`, permission `customers.read`) and a navigation link.
- Unit tests: backend customer-read person fields (API test); frontend service + store (URLs,
  payloads, write-through refetch, balance/outstanding derivations).

Non-goals: maintaining customer stats from orders (`total_spent`/`order_count`/`last_purchase_at`
are shown read-only, the backend owns them); auto-creating a credit when an order is left on fiado;
linking credit payments to the POS cash drawer; a full person-management API (only the read embed is
added); and realtime/auto-refresh. Customers are tenant-scoped, so there is no branch scoping.

## Capabilities

### New Capabilities
- `frontend-customers`: the customers frontend — a customer directory (create with inline person,
  edit, deactivate, search), free-form preferences, and store credit (fiado) with credit
  registration and settlement payments, tenant-scoped and gated by `customers.read` /
  `customers.manage`, with the settling employee chosen from staff.

### Modified Capabilities
- `customer-management`: customer reads SHALL return the person's identity fields (name, document,
  phone, email) embedded in the customer response, so a client can display and search customers by
  name — closing the gap where only `person_id` was exposed.

## Impact

- **Backend code**: `modules/customers/infrastructure/api/schemas.py` (CustomerResponse fields),
  `modules/customers/domain/entities.py` (optional person fields on the `Customer` read entity),
  `modules/customers/infrastructure/repositories.py` (load person on read; populate on create),
  `modules/customers/infrastructure/models.py` (a `person` relationship for eager loading), and
  `tests/modules/customers/test_customers_api.py` (assert the new fields).
- **Frontend code**: new `front/src/services/customers.api.ts`, `front/src/stores/customers.ts`,
  `front/src/views/CustomersView.vue`, and `front/src/components/customers/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the staff store (employee picker for settlement payments), the shared `http` axios
  instance, `@/lib/money` `formatCOP`, and the `apiError` helpers. No active-branch context.
- **Permissions/RBAC**: relies on `customers.read` and `customers.manage`; settlement reads staff
  data. No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
