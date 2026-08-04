## Context

The `cash` module has ORM models (`cash_sessions`, `cash_movements`) and domain dataclasses but no functional layer. The `menu`/`staff`/`inventory`/`recipes`/`orders` modules are the established hexagonal reference; this change mirrors them. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English-only identifiers, "small complete system".

Facts confirmed in code:
- Both tables are branch-scoped (`BranchScopedMixin`). `cash_sessions` has `opening_amount`, optional `counted_amount`/`expected_amount`/`difference`, `status`, `opened_at` (server-defaulted), `closed_at`, and opening/closing employee FKs. `cash_movements` has `cash_session_id`, `type`, `concept`, `amount`, `method`, and a loose `reference_id` (no FK).
- The only cross-module dependency is `employees` (staff ✅). `branches` is validated too.
- Permissions `cash.read` / `cash.open` / `cash.close` / `cash.move` already exist in the catalog.
- Entities already largely follow the convention, except `CashSession.opened_at` is required — it should be optional (server-defaulted), like staff's `hired_at`.
- `cash` is registered in `models_registry.py`; tables exist in migration `0002`. Shared `ValidationError` (→422) exists.
- The Colombia context matters: common methods include cash plus Nequi/Daviplata/card, which are NOT physical drawer cash.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for the cash open/close (arqueo) lifecycle and movement ledger.
- One-open-session-per-branch invariant; status guards; reconciliation on close.
- Tenant/branch isolation, reference validation, RBAC.
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- **Orders → cash payment integration** — registering an order payment as a `cash_movement` of concept `sale`. Future `integrate-orders-cash` change.
- Multiple registers per branch (no "register" entity exists; one open session per branch).
- Per-method drawer reconciliation beyond the cash/non-cash split (see Decisions).
- Expense/withdrawal approval workflows.

## Decisions

**1. Mirror the `inventory` module layout; one `CashService`.**
`domain/ports.py` (`CashRepository` Protocol), `application/use_cases/manage_cash.py` (`CashService`), `infrastructure/repositories.py` (`SqlAlchemyCashRepository`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency with five working references.

**2. One open session per branch is the core invariant.**
There is no per-register entity, so a branch has at most one `open` cash session. `open_session` checks for an existing open session (→ `ConflictError`); `get_open_session` powers "where do payments go". Rationale: matches how a single POS/branch operates at pilot scale; avoids ambiguity about which session a movement belongs to.

**3. `expected_amount` reconciles physical cash only.**
On close, `expected_amount = opening_amount + Σ(in where method=cash) − Σ(out where method=cash)`, and `difference = counted_amount − expected_amount`. Non-cash movements (card, Nequi, Daviplata) are recorded for reporting but do not affect the drawer count, because *arqueo* reconciles physical cash. A `CASH_METHOD = "cash"` constant defines the drawer method. Rationale: correct for the Colombian payment mix; counting card/Nequi against a physical drawer would always show a false difference. Alternative (sum all methods) rejected as semantically wrong for a cash count.

**4. Movements are recorded as-is; the session is the consistency boundary.**
A movement requires an `open` session (guard) and a positive amount; `type` ∈ {in, out}. Unlike inventory, cash does not maintain a running cached balance column — `expected_amount` is computed at close from the movement ledger. Rationale: the ledger is the source of truth; a session is short-lived (one shift) so on-the-fly computation is cheap and avoids drift.

**5. Validation split: Pydantic for shape, service for business rules.**
Pydantic: `type` literal in/out, `amount` `> 0`, `opening_amount`/`counted_amount` `≥ 0`, required fields. Service: reference existence (branch/employee) in tenant, one-open-session invariant, status guards, reconciliation math. Errors reuse `shared/domain/errors`.

**6. Employees passed explicitly and validated.**
`opened_by_employee_id` (open) and `closed_by_employee_id` (close) are supplied in the request and validated against the tenant, mirroring how other modules pass `employee_id`/`branch_id` explicitly (no actor→employee resolution yet).

## Risks / Trade-offs

- **Concurrent opens on the same branch** could both pass the "no open session" check and create two open sessions. → Acceptable at pilot scale (one POS/branch); a later hardening can add a partial unique index on `(branch_id) WHERE status='open'`. Logged as an open question.
- **Cash-only `expected_amount`** means non-cash totals are not reconciled here → intended; per-method totals can be added to the close response or a report later without schema change (the `method` column already exists).
- **No running balance** means listing "current expected" mid-shift requires summing movements → fine; a read endpoint can expose it if needed.
- **sqlite vs Postgres** → `Numeric` arithmetic and FK constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change expected — both tables exist in migration `0002`. After implementation, an `alembic revision --autogenerate` should be a no-op for cash (live run needs Postgres; otherwise verify statically).
2. Deploy is additive — new `/cash` endpoints, router included in `main.py`. Reverting the code removes the endpoints.

## Open Questions

- Harden the one-open-session invariant with a DB partial unique index now, or defer? (Default: defer.)
- Should the close response include a per-method breakdown (cash vs card vs Nequi) for the daily report? (Default: out of scope now; add when reporting is built.)
- Should opening a session require that the previous one be closed by the same employee / same shift? (Default: no such constraint.)
