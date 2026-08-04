## Why

The `/shifts` view ("Gestión de turnos") is a static in-memory prototype: recurring weekly patterns, days off, coverage and requests all live in the browser and vanish on reload. The backend already has flat per-date `planned_shifts` but no recurring pattern, no day-off/coverage concept, and no request workflow — so the screen cannot actually control real schedules. Pilot restaurants need a real system to run rest days, días libres, coverage and time-off requests without falling back to paper.

## What Changes

- Introduce a **recurring shift template** per employee (which weekdays + entry/exit times + validity). The template is the source of truth; rest days are the weekdays it omits. It is recurring and indefinite (`valid_until = null`) — the schedule repeats forward until an admin changes it.
- **Materialize** concrete `planned_shifts` from templates over a rolling **90-day horizon**, with an easy **"extend +90 days"** action that advances a `generated_through` watermark (and again, and again).
- Editing a template **regenerates future shifts without overwriting** shifts already marked day-off or covered.
- Model **day-off / special-hours / coverage as status on the shift** (not a separate table): `status` (scheduled | day_off | covered | manual) + `origin` (template | manual | coverage) + `covered_by_employee_id`. Coverage creates a **new shift for the substitute** (`status = covered`) while the absentee's shift becomes `day_off` — preserving who was originally scheduled and who covered.
- Add a **time-off request** workflow (`time_off_request`: employee, date, reason, status pending/approved/rejected, decided_by). Approving flips the shift to day-off and optionally assigns coverage.
- Add a **week-range read endpoint** `GET /staff/shifts?branch_id&from&to` (today shifts are only listable per-employee with no range) — the query that paints the calendar.
- **Wire the `/shifts` screen to real data**: the Calendario board reads/writes real shifts; the Solicitudes inbox drives the request workflow; the Plantillas editor authors templates. Delivered in three phases.
- Out of scope for now: employee color and operational shift-role tag (Caja/Cocina/…). The employee's name (resolved via `rbac.api`) is enough to render rows.

## Capabilities

### New Capabilities
- `shift-scheduling`: recurring shift templates, materialization over a rolling horizon with extend, day-off/special/coverage as shift status, time-off request workflow, coverage assignment, and the week-range read endpoint. Backend (staff module).
- `frontend-shifts`: the `/shifts` board wired to real data — Calendario (line-up board over real shifts), Solicitudes (request inbox), and Plantillas (template editor), delivered in phases.

### Modified Capabilities
- `staff-management`: the existing `planned_shift` gains `status`, `origin` and `covered_by_employee_id`; day-off/coverage semantics and the new week-range list endpoint change the documented shift requirements.

## Impact

- **Backend** (`modules/staff`): new `shift_template` and `time_off_request` tables/entities; `planned_shift` gains columns; new domain ports, use cases, repositories, API routes and schemas; a generation service; an Alembic migration; `scripts/seed`/`seed_demo` gain templates + generated shifts. Permissions: reads `staff.read`, writes `staff.manage`.
- **Frontend** (`views/ShiftsView.vue`, `services/staff.api.ts`, `stores/staff.ts`): replace in-memory seed with real API-backed state; add template/request/coverage service calls and a shift-scheduling store; the three views (Calendario/Solicitudes/Plantillas) consume it.
- **API contract**: additive endpoints under `/staff` plus additive fields on `PlannedShiftResponse`; no breaking removals.
- **Docs**: add `docs/staff/` module docs for the new shift-scheduling surface.
