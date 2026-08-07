## 1. Backend: embed person identity on customer reads

- [x] 1.1 Load the backing person on customer reads (implemented as an explicit `_person_for` lookup + a join in `list_customers`, rather than an ORM relationship — avoids async lazy-load pitfalls)
- [x] 1.2 Add optional `first_name`, `last_name`, `document_number`, `phone`, `email` fields to the `Customer` read dataclass (`modules/customers/domain/entities.py`)
- [x] 1.3 In `modules/customers/infrastructure/repositories.py`: eager-load the person (`selectinload`) in `list_customers` and `get_customer`; populate the five fields in the `_customer(model)` mapper from `model.person`; populate them on `create_customer` from the just-created person
- [x] 1.4 Add the five fields to `CustomerResponse` (`modules/customers/infrastructure/api/schemas.py`) as optional, so the existing `model_validate(..., from_attributes=True)` mapping carries them
- [x] 1.5 Update `tests/modules/customers/test_customers_api.py` to assert create/list/get responses include `first_name`/`last_name` (and document/phone/email when provided); run the customers backend tests green

## 2. Frontend service layer

- [x] 2.1 Create `front/src/services/customers.api.ts` with types `Customer` (incl. person fields + `total_spent`/stats), `Preference`, `Credit`, `CreditPayment` (money fields typed as `string`)
- [x] 2.2 Add customer calls: `listCustomers(active?)`, `getCustomer(id)`, `createCustomer(input)`, `updateCustomer(id, patch)`, `deactivateCustomer(id)` (`DELETE`)
- [x] 2.3 Add preference calls: `listPreferences(customerId)`, `setPreference(customerId, { key, value })`, `removePreference(prefId)`
- [x] 2.4 Add credit + payment calls: `listCredits(customerId)`, `getCredit(creditId)`, `registerCredit(customerId, input)`, `listCreditPayments(creditId)`, `registerCreditPayment(creditId, input)`
- [x] 2.5 Add service unit tests in `front/src/services/__tests__/customers.api.spec.ts` (URLs, payloads, the active param, nested credit/payment paths, returned shapes)

## 3. Frontend store layer

- [x] 3.1 Create `front/src/stores/customers.ts` (Pinia options) state: `customers`, `selectedCustomerId`, `preferences`, `credits`, `paymentsByCredit`
- [x] 3.2 Add `loadCustomers()`, `selectCustomer(id)` (loads preferences + credits); add `customerName(c)`, `activeCustomers` getters
- [x] 3.3 Add customer mutations `createCustomer` / `updateCustomer` / `deactivateCustomer` (write-through refetch customers)
- [x] 3.4 Add preference mutations `setPreference` / `removePreference` and credit mutations `registerCredit` (refetch the customer's credits) and `loadPayments` / `registerCreditPayment` (refetch the credit + its payments)
- [x] 3.5 Add `creditBalance(creditId)` and `customerOutstanding` getters (integer-cents)
- [x] 3.6 Add store unit tests: customers load + name, write-through refetch for customer/preference/credit/payment, credit-balance and customer-outstanding derivations

## 4. Frontend screen, components, routing

- [x] 4.1 Add `/customers` route (name `customers`, `meta.permission: 'customers.read'`) in `front/src/router/index.ts` and a nav link (`Clientes`) in `front/src/components/AppSidebar.vue`
- [x] 4.2 Create `front/src/views/CustomersView.vue` container + `CustomersPanel.vue` orchestrator: load customers + staff, master list (name + document/phone, active filter, name/document search, drill-down), refresh, error
- [x] 4.3 Create the new-customer dialog (gated by `customers.manage`): first/last name, optional document/phone/email
- [x] 4.4 Create `CustomerDetail.vue`: identity (read-only) + deactivate/reactivate; the preferences section (key/value add/remove)
- [x] 4.5 Create the fiado section in the detail: register-credit control, credits list with payment status + outstanding balance, and a register-payment control (amount currency, method, employee picker) showing the balance
- [x] 4.6 Render money via `formatCOP`; resolve employee names from staff; surface API errors with friendly messages (reuse `apiError` helpers); show `total_spent`/stats read-only

## 5. Verification

- [x] 5.1 Backend customers tests green; frontend `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 5.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 5.3 Manual smoke against the running backend: create a customer (name shows in the list) → add a preference → register a fiado credit → register a partial then full settlement payment (status pending→partial→paid, balance falls) → deactivate; verify a read-only user sees no manage controls
