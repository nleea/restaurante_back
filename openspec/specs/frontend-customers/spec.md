# frontend-customers

## Purpose

The customers frontend — the client for the backend `/customers` module, living on the light office
working surface. Customers are tenant-scoped (no branch). It is a master–detail screen: a customer
**directory** (master) showing each customer's name and a document/phone, with an active filter and a
client-side name/document search and a create action (inline person: first/last name plus optional
document, phone, email); and a per-customer **detail** with three sections — identity (read-only,
since the backend update accepts only the active state and user link, so identity is set at creation)
with a deactivate/reactivate action, **preferences** (free-form key/value CRM notes, add/remove), and
**fiado** (store credit): register a credit, list a customer's credits with their payment status and
outstanding balance, and register settlement payments (amount, method, employee) with the balance
shown. Customer reads carry the person identity (a backend embed added by this change), so names
resolve directly. Money fields (`total_spent`, credit `total_amount`, payment `amount`) render with
`formatCOP`; the only client arithmetic is a credit's outstanding balance (`total_amount − Σ
payments`) and a customer's total outstanding across not-`paid` credits, summed in integer cents,
while the server's `payment_status` stays authoritative. The settling employee is chosen from staff.
The screen is reached with `customers.read`; all create/edit/deactivate/preference/credit/payment
controls are gated by `customers.manage` — UX gating only, the backend enforces authorization
independently. Order-derived stats (`total_spent`/`order_count`/`last_purchase_at`) are shown
read-only; auto-fiado on order close, POS-cash-linked credit payments, and a full person-edit API are
out of scope for this slice.

## Requirements

### Requirement: Customers service layer

The Customers API service SHALL expose typed functions covering the `/customers` endpoints:
customers — create (`POST /customers`), list (`GET /customers`, optional `active` filter), get
(`GET /customers/{id}`), update (`PATCH /customers/{id}`) and deactivate
(`DELETE /customers/{id}`); preferences — set (`POST /customers/{id}/preferences`), list
(`GET /customers/{id}/preferences`) and remove (`DELETE /customers/preferences/{prefId}`); credits —
register (`POST /customers/{id}/credits`), list (`GET /customers/{id}/credits`) and get
(`GET /customers/credits/{creditId}`); and credit payments — register
(`POST /customers/credits/{creditId}/payments`) and list
(`GET /customers/credits/{creditId}/payments`). Money fields SHALL be carried as the backend sends
them (string-encoded decimals) without lossy reformatting in transport.

#### Scenario: Create a customer with inline person

- **WHEN** `createCustomer({ first_name, last_name, document_number?, phone?, email?, user_id? })`
  is called
- **THEN** it POSTs `/customers` and resolves with the created `Customer` carrying its person fields

#### Scenario: Deactivate a customer

- **WHEN** `deactivateCustomer(id)` is called
- **THEN** it DELETEs `/customers/{id}` and resolves with the updated `Customer`

#### Scenario: Set and remove a preference

- **WHEN** `setPreference(customerId, { key, value })` is called
- **THEN** it POSTs `/customers/{customerId}/preferences`; `removePreference(prefId)` DELETEs
  `/customers/preferences/{prefId}`

#### Scenario: Register a credit and list a customer's credits

- **WHEN** `registerCredit(customerId, { total_amount, reference_id? })` is called
- **THEN** it POSTs `/customers/{customerId}/credits` and resolves with the created `Credit`;
  `listCredits(customerId)` GETs `/customers/{customerId}/credits`

#### Scenario: Register and list credit payments

- **WHEN** `registerCreditPayment(creditId, { amount, method, employee_id })` is called
- **THEN** it POSTs `/customers/credits/{creditId}/payments`; `listCreditPayments(creditId)` GETs
  `/customers/credits/{creditId}/payments`

### Requirement: Customers store

The Customers store SHALL hold the tenant's customers (with their person identity), the selected
customer's preferences and credits, and the selected credit's payments. Mutations (create/update/
deactivate customer, set/remove preference, register credit, register payment) SHALL be
write-through: after a successful call the store refetches the affected collection so server state is
shown verbatim.

#### Scenario: Load customers

- **WHEN** the store loads customers
- **THEN** `customers` holds the tenant's customers including each one's name and contact

#### Scenario: Registering a credit refreshes the customer's credits

- **WHEN** a credit is registered for the selected customer
- **THEN** the store refetches that customer's credits so the new credit appears

#### Scenario: Registering a payment refreshes the credit and its payments

- **WHEN** a settlement payment is registered against a credit
- **THEN** the store refetches that credit and its payments so the payment status and balance update

### Requirement: Credit balance derivations

The store SHALL derive client-side, for a credit, its outstanding balance (`total_amount` minus the
sum of its payments, in integer cents) and, for a customer, the total outstanding across their
not-yet-`paid` credits, presenting these as guidance while the server's `payment_status` remains
authoritative.

#### Scenario: Credit balance reflects payments

- **WHEN** a credit with a known total has payments registered
- **THEN** the derived outstanding balance equals the total minus the sum of payments

#### Scenario: Customer outstanding sums unpaid credits

- **WHEN** a customer has more than one credit not fully paid
- **THEN** the customer's total outstanding equals the sum of those credits' balances

### Requirement: Customer directory

The CustomersView SHALL list the tenant's customers showing each one's name and a document or phone,
with an active filter and a client-side search by name or document, and let an authorized user create
a customer (first and last name, optional document, phone, email) and deactivate or reactivate one;
these mutations SHALL require the `customers.manage` permission. (The backend update accepts only the
active state and user link, so customer identity is set at creation, not edited here.)

#### Scenario: Create a customer

- **WHEN** a user with `customers.manage` submits the new-customer form with a first and last name
- **THEN** the customer is created and appears in the directory with its name

#### Scenario: Search the directory

- **WHEN** the user types a name or document fragment in the search
- **THEN** only matching customers are shown

#### Scenario: Deactivate a customer

- **WHEN** a user with `customers.manage` deactivates a customer
- **THEN** the customer's row reflects an inactive state

### Requirement: Customer preferences

The CustomersView SHALL show a selected customer's free-form key/value preferences and let an
authorized user add and remove them; these mutations SHALL require the `customers.manage` permission.

#### Scenario: Add a preference

- **WHEN** a user with `customers.manage` adds a key/value preference
- **THEN** the preference appears in the customer's preferences

#### Scenario: Remove a preference

- **WHEN** a user with `customers.manage` removes a preference
- **THEN** the preference is no longer shown

### Requirement: Store credit (fiado) and settlement

The CustomersView SHALL let an authorized user register a store credit for a customer (positive
total amount), list the customer's credits with their payment status and outstanding balance, and
register settlement payments against a credit (positive amount, method, employee); these mutations
SHALL require the `customers.manage` permission and the balance SHALL be shown while registering a
payment.

#### Scenario: Register a credit

- **WHEN** a user with `customers.manage` registers a credit with a positive amount
- **THEN** the credit appears with `payment_status` `pending` and its full amount outstanding

#### Scenario: Settle a credit

- **WHEN** a user with `customers.manage` registers a payment against a credit
- **THEN** the credit's payment status and outstanding balance update (partial, then paid when the
  total is reached)

### Requirement: Permission gating and navigation

The Customers screen SHALL be reachable at `/customers` only for authenticated users with
`customers.read`, exposed via a navigation entry; the create/edit/deactivate customer, preference
add/remove, credit register, and payment controls SHALL be shown only with `customers.manage`. This
gating is UX — the backend enforces authorization independently.

#### Scenario: Read-only customers user

- **WHEN** the current user has `customers.read` but not `customers.manage`
- **THEN** the directory, preferences, and credits are visible read-only and no mutating actions are
  shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `customers.read` navigates to `/customers`
- **THEN** the router redirects them to the forbidden view
