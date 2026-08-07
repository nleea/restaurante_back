## 1. Service layer

- [x] 1.1 Add `OrderPayment` interface and `PaymentMethod` type/constant (Efectivo, Nequi, Daviplata, Tarjeta, Transferencia) to `front/src/services/orders.api.ts`
- [x] 1.2 Add `registerPayment(orderId, { amount, method, employee_id, diner_reference? })` → `POST /orders/{orderId}/payments`
- [x] 1.3 Add `listPayments(orderId)` → `GET /orders/{orderId}/payments`
- [x] 1.4 Add service unit tests in `front/src/services/__tests__` covering both calls (URL, payload, returned shape)

## 2. Store layer

- [x] 2.1 Add `paymentsByOrder: Record<string, OrderPayment[]>` to `OrdersState` in `front/src/stores/orders.ts`
- [x] 2.2 Add getters `paymentsOf(orderId)`, `paidOf(orderId)` (Σ amounts), and `balanceOf(orderId)` (`max(0, total − paid)`)
- [x] 2.3 Add `fetchPayments(orderId)` action that loads payments into state
- [x] 2.4 Add `registerPayment(orderId, input)` action: guard `currentEmployee`, POST, then write-through refetch payments + order header
- [x] 2.5 Refetch payments wherever an order's items are loaded (e.g. extend `refreshOrder` / ticket open) so the panel stays fresh
- [x] 2.6 Add store unit tests: paid/balance derivation, fully-settled clamps to 0, write-through refetch, and 409 propagation

## 3. Payment panel UI (OrderTicket)

- [x] 3.1 Add `canPay = auth.can('orders.pay')` and load payments when the ticket mounts/selects an order
- [x] 3.2 Render summary: total / paid / outstanding balance using the existing COP formatter
- [x] 3.3 Render the registered-payments list (method label, amount, diner reference when present)
- [x] 3.4 Add registration form (gated by `canPay`): method selector, amount prefilled with balance, optional diner reference, submit button
- [x] 3.5 On submit call `store.registerPayment`; on success reset/prefill the form from the new balance
- [x] 3.6 Map `isConflict` (409) to the "no open cash session" message and keep form values for retry; show generic error otherwise
- [x] 3.7 Settlement guidance: warn near "Cerrar comanda" when balance > 0; present close as next step when balance is 0

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: open order → add items → register partial then full payment → balance reaches 0 → close; and a 409 path with no open cash session
