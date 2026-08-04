## Context

The staff module already ships flat, per-date `planned_shifts` (`POST/GET /staff/employees/{id}/shifts`, `PATCH/DELETE /staff/shifts/{id}`), plus `attendances` that link to a `planned_shift_id`, and `commissions`. The frontend already has a typed layer (`staff.api.ts`) for these. What is missing is everything that makes a *schedule*: a recurring pattern, rest days, days off, coverage, and a request/approval loop. The `/shifts` prototype models all of this in memory (plantilla → generated shift → exception → solicitud) but persists nothing.

The core tension: the prototype treats a recurring **template** as the source of truth and computes shifts; the backend treats each **shift** as a stored row. Both cannot be the source of truth. `attendances` already foreign-keys a concrete shift row, which is decisive.

Constraints: hexagonal architecture (`API → application → domain`, `infrastructure` implements ports), domain stays framework-free, row-level `tenant_id` + `branch_id` on every business entity (`BranchScopedMixin`), English-only identifiers, RBAC (`staff.read` / `staff.manage`), multi-branch by data model.

## Goals / Non-Goals

**Goals:**
- A recurring, indefinite weekly template per employee that generates real shift rows going forward.
- Materialized shifts over a rolling 90-day horizon, trivially extendable by another 90 days, repeatedly.
- Day-off, special-hours and coverage expressed on the shift itself; coverage preserves the audit trail (who was scheduled, who covered).
- A time-off request workflow (request → approve/reject → optional coverage) with its own history.
- A week-range read endpoint that paints the calendar in one call.
- Wire `/shifts` to real data in phases without a big-bang rewrite.

**Non-Goals:**
- Employee color and operational shift-role tag (Caja/Cocina/…) — deferred; name (resolved via `rbac.api`) is enough.
- Background/cron auto-generation — the horizon is advanced by an explicit admin action for pilots.
- Payroll, overtime rules, labor-law validation, shift swapping between employees beyond coverage.
- Attendance/commissions changes beyond the additive shift fields they already reference.

## Decisions

### D1 — Template authors; shifts are materialized rows (hybrid, not pure-computed)

`shift_template` (recurring: `weekdays[]`, `start_time`, `end_time`, `valid_from`, `valid_until = null`) is the authoring surface. A generation service writes concrete `planned_shift` rows for each matching date within the horizon. **Why over pure-computed (compute shifts on read):** `attendances` already link to `planned_shift_id`; computed shifts have no row to link, and reads become a plain range query instead of a per-request generation. **Why over template-only-as-UI (Path A):** loses the recurring source of truth and still needs new backend for days-off/requests anyway.

Rest days need no row: a weekday absent from the template simply produces no shift ("día de descanso"). A day off is different — it is a would-be-scheduled shift whose `status` becomes `day_off`.

### D2 — Exceptions are status on the shift, not a separate table

`planned_shift` gains:
- `status`: `scheduled | day_off | covered | manual`
- `origin`: `template | manual | coverage`
- `covered_by_employee_id`: nullable FK (set when `status = covered`)
- `note`: nullable text (motive / "Refuerzo por evento")

One row is the single truth per `(employee, date)` slot. **Why over a `shift_exceptions` table:** fewer moving parts, no join to resolve a cell, and the regeneration rule becomes "don't touch rows whose `status != scheduled` or `origin != template`."

### D3 — Coverage creates a new shift for the substitute

When employee A is off and B covers: A's shift becomes `status = day_off`; a **new** `planned_shift` for B is created with `status = covered`, `origin = coverage`, `covered_by_employee_id = A`. **Why over reassigning A's row to B:** preserves who was originally scheduled and who stepped in — required for "control everything" and future payroll/attendance attribution. Trade-off: two rows for one slot; the range query returns both and the UI renders A's as día-libre-cubierto and B's as covering.

### D4 — Rolling horizon with a `generated_through` watermark

Each template (or branch) tracks `generated_through` (a date). Generation fills shifts from `max(valid_from, last_generated+1)` up to `today + 90d`. An **"extend +90"** action advances the target and generates the next window. **Why:** indefinite templates can't materialize infinitely; a watermark makes generation idempotent and the extension a one-click, repeatable admin action. Generation is idempotent — re-running never duplicates a `(employee, date)` shift.

### D5 — Regeneration preserves resolved slots

Saving/editing a template regenerates **future** shifts (`date >= today`, or an explicit effective date) but **never overwrites** rows where `status != scheduled` or `origin != template` (approved day-offs, coverage, manual shifts survive). Past shifts are immutable. **Why:** matches the brief's "¿Aplicar nueva plantilla? Los días libres ya aprobados se conservan" and protects attendance-linked history.

### D6 — Time-off requests are a separate table

`time_off_request` (`employee_id`, `date`, `reason`, `status: pending|approved|rejected`, `decided_by`, `decided_at`, `note`). Approving sets the target shift to `day_off` and, if a substitute is chosen, creates the coverage shift (D3). Rejecting records the reason and leaves the shift scheduled. **Why separate from the shift:** a request has its own lifecycle and audit trail, can exist before a decision, and a rejected request must not mutate the schedule.

### D7 — Week-range read endpoint

Add `GET /staff/shifts?branch_id=&from=&to=` returning all shifts for the branch in the date window (across employees), plus `GET /staff/time-off-requests?branch_id=&status=`. **Why:** the calendar needs one branch-scoped range call, not N per-employee calls. The existing per-employee list endpoint stays for the employee self-view.

### D8 — Coverage availability derives from templates + shifts

"Who can cover date D?" = active employees in the branch whose template does not schedule weekday(D) **and** who have no shift row on D. Computed server-side for the request/coverage UI. **Why server-side:** the client would otherwise need every template to compute availability.

### D9 — Frontend phasing

- **Phase 1 (frontend-shifts + backend):** Calendario reads the range endpoint and writes real shifts (manual create, mark day-off, assign coverage, edit hours, remove). Templates seeded via script so the calendar has data.
- **Phase 2:** Solicitudes inbox over `time_off_request` (approve/reject/assign coverage); employee self-view can create a request.
- **Phase 3:** Plantillas editor authors/edits templates and triggers regeneration + "extend +90".

A new Pinia `shifts` store owns week state and API calls; `ShiftsView.vue` swaps its in-memory seed for store-backed data, keeping the El Pase visual model (mono role tag, coverage heat lamp) intact.

## Risks / Trade-offs

- **Regeneration corrupting resolved slots** → D5 hard rule: generation only writes missing dates and only touches `origin = template && status = scheduled` rows; covered by tests over the preserve-cases.
- **Duplicate shifts on repeated generation** → idempotent generator keyed on unique `(tenant_id, employee_id, shift_date)`; enforce with a DB unique constraint.
- **Two rows per covered slot confusing the UI** → the range payload marks each row's `status`/`covered_by`; the client already distinguishes día-libre-cubierto vs covering chits.
- **Editing a template mid-week** → only future dates (>= effective date) regenerate; today's already-started shifts and past shifts are immutable.
- **Horizon never extended → schedule silently ends** → surface `generated_through` in the UI and warn when the visible week approaches it; the "extend +90" action is one click.
- **Timezone drift on `shift_date`/times** → store dates/times in the tenant's local terms (naive `date`/`time` as today), consistent with existing `planned_shift`; no UTC conversion for wall-clock schedule.

## Migration Plan

1. Alembic migration: create `shift_templates`, `time_off_requests`; add `status` (default `scheduled`), `origin` (default `manual` for pre-existing rows), `covered_by_employee_id`, `note` to `planned_shifts`; add unique `(tenant_id, employee_id, shift_date)` on `planned_shifts` (dedupe any existing collisions first). Register new models in `migrations/env.py`.
2. Backfill: existing `planned_shifts` → `status='scheduled'`, `origin='manual'` (they were hand-created, not template-generated).
3. Seed: `scripts/seed`/`seed_demo` create templates for demo employees and generate the 90-day horizon so the calendar is populated.
4. Ship backend + Phase 1 frontend behind the existing `staff.read`/`staff.manage` gates. Rollback = drop new tables/columns; the additive `PlannedShiftResponse` fields are backward-compatible with the current frontend.

## Open Questions

- Should `generated_through` live per-template or per-branch? (Leaning per-template for isolation; per-branch is simpler to extend in one action.)
- Effective date of a template edit: always "from today" or admin-chosen? (Brief implies from an effective date; default to today for Phase 3.)
- Do we expose employee self-service request creation in Phase 2, or admin-only requests first? (Brief has a self-view; can gate by a lighter permission later.)
