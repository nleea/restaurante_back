## Why

Orders already post their payments to the cash drawer (a `sale` cash movement on the branch's open
session), but the two *other* ways real cash moves at the counter do not: **paying a supplier**
(purchasing) and **settling a customer's fiado** (customer credit). Today those payments are
recorded only in their own ledgers, so cash that physically leaves or enters the drawer for them is
invisible to the caja — and the close-of-shift **arqueo will not reconcile**. This closes that gap
by mirroring the existing orders→cash wiring for purchasing and fiado.

## What Changes

- **Purchasing → Cash (backend)**: when a purchase payment is registered with `method = cash`, the
  system SHALL also post a cash movement of type `out`, concept `purchase_payment`, on the open cash
  session of the **purchase order's branch**, referencing the order — written atomically with the
  payment. If the branch has no open cash session, the cash payment is rejected (conflict), exactly
  as an order cash payment is. Non-cash methods (card, transfer, Nequi) are unchanged — no cash
  movement, no session requirement.
- **Fiado → Cash (backend)**: when a customer credit settlement payment is registered with
  `method = cash`, the system SHALL also post a cash movement of type `in`, concept
  `credit_payment`, on the open cash session of the **paying employee's branch** (customer credits
  are tenant-level and carry no branch, so the branch is resolved from the employee handling the
  cash), referencing the credit — written atomically. No open session → conflict. Non-cash methods
  unchanged.
- **Frontend (polish)**: the purchasing and customers payment dialogs surface the new
  "no hay caja abierta" conflict with a clear message; the cash ledger labels the new
  `purchase_payment` / `credit_payment` concepts (and the existing `sale`) in Spanish instead of
  raw codes. No new screens.
- Tests: backend — purchase/fiado cash payment writes a matching movement on the open session,
  reflects in the drawer's expected amount, and is rejected when no session is open; non-cash makes
  no movement. Frontend — the cash ledger concept labels.

Non-goals: posting finance expenses to the cash drawer (an explicit "independent ledger" decision);
auto-creating a fiado credit when an order is left unpaid; reversing/voiding a posted payment and its
cash movement; backfilling cash movements for payments recorded before this change; and changing the
cash module's own endpoints (the integration is written from the paying modules, as orders already
do).

## Capabilities

### Modified Capabilities
- `purchasing-management`: the **Register purchase payments** requirement gains that a `cash`-method
  payment posts a cash `out` (concept `purchase_payment`) on the order branch's open session and
  requires one — so supplier cash payments leave the drawer in the caja.
- `customer-management`: the **Settle credit with payments** requirement gains that a `cash`-method
  payment posts a cash `in` (concept `credit_payment`) on the paying employee's branch open session
  and requires one — so fiado cash settlements enter the drawer in the caja.

## Impact

- **Backend code**: `modules/purchasing/` — its repository gains an open-session lookup + a
  CashMovement write on cash payments (importing the cash models, as orders does), and the
  `register_payment` use case resolves the order's branch and requires an open session for cash;
  `modules/customers/` — same, resolving the branch from the paying employee
  (`EmployeeModel.branch_id`); plus their API tests. Reuses `CashSessionModel` / `CashMovementModel`
  and the `ConflictError` pattern from orders.
- **Frontend code**: friendlier 409 messages in `components/procurement/OrdersArea.vue` and
  `components/customers/CustomerDetail.vue` payment dialogs; concept labels in
  `components/cash/ActiveDrawer.vue` (and the history detail). Small, no new files required (a tiny
  shared concept-label map may be added).
- **Backend behavior change (intentional)**: a `cash` purchase/fiado payment now **requires an open
  cash session** and will 409 without one — consistent with orders. Non-cash payments are
  unaffected.
- **Permissions/RBAC**: unchanged (`purchasing.manage`, `customers.manage`, and the cash write is an
  internal cross-module post, not a new endpoint).
- **Dependencies**: none.
