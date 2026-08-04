## Why

Cash (caja / arqueo) is the next node on the critical path: it is where money is reconciled at the end of every shift, and it is the hard dependency blocking **order payments** (`order_payments.cash_session_id` is a required FK to `cash_sessions`). Pilot restaurants cannot close a day without a cash count. The module exists today only as a data layer (`cash_sessions`, `cash_movements`) with no functional layer. Its only dependency — `employees` — is already implemented, so cash can be built now and immediately unblocks the future orders↔cash payment integration.

## What Changes

- Add the **application + API layer** for the cash module, mirroring the reference modules (hexagonal).
- **Cash sessions**: open a register session for a branch with an opening float (`opening_amount`) and the opening employee; get a session; list sessions (filter by branch/status); get the current open session of a branch; close a session by entering the physically counted amount.
- **Cash movements**: while a session is `open`, register movements of type `in`/`out` with a concept, a positive amount, a payment method, and an optional loose `reference_id` (bridge to an order/expense, no FK); list a session's movements.
- **Reconciliation (arqueo)**: on close, the system computes `expected_amount` from the opening float plus cash movements in/out, sets `difference = counted_amount − expected_amount`, stamps `closed_at` and the closing employee, and marks the session `closed`.
- Enforce the **one-open-session-per-branch** invariant (opening while one is already open → conflict) and status guards (movements only on `open` sessions; cannot close twice).
- Enforce **multi-tenant + multi-branch isolation** (tenant from middleware; `branch_id` validated against the tenant) and **RBAC** with the existing `cash.read` / `cash.open` / `cash.close` / `cash.move` permissions.
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `cash` registration in `models_registry.py` already exist (entities get a minor convention tidy: make `opened_at` optional, server-defaulted).

### Explicitly out of scope (deferred)
- **Orders → cash payment integration** (`order_payments` writing a `cash_movement` of concept `sale`) — a focused change after this one. Cash here only provides the session + movement primitives.

## Capabilities

### New Capabilities
- `cash-management`: Branch-scoped cash register sessions with an open/close (arqueo) lifecycle and a movement ledger — tenant-isolated and RBAC-protected. Order-payment integration is out of scope.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/cash/`: `domain/ports.py`, `application/use_cases/manage_cash.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; minor restructure of `domain/entities.py` (`opened_at` optional).
- **Modified**: `src/restaurante/main.py` (include `cash_router`).
- **Depends on** existing tables `employees` (staff), `branches` — validated for existence; and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **APIs**: new `/cash/*` endpoints (sessions + movements). No breaking changes.
- **Unblocks**: a later `integrate-orders-cash` change can register payments against an open session.
- **Tests**: new integration suite under `tests/modules/cash/` (sqlite, FK enforcement).
