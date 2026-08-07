## 1. Backend — data model & migration

- [x] 1.1 Add `ShiftTemplate` and `TimeOffRequest` domain entities (`modules/staff/domain/entities.py`); extend `PlannedShift` with `status`, `origin`, `covered_by_employee_id`, `note`
- [x] 1.2 Add ORM models (`infrastructure/models.py`) using `BranchScopedMixin` for `shift_templates` and `time_off_requests`; add columns + unique `(tenant_id, employee_id, shift_date)` to `planned_shifts`; register modules in `migrations/env.py`
- [x] 1.3 Alembic autogenerate migration; backfill existing `planned_shifts` to `status='scheduled'`, `origin='manual'`; dedupe any slot collisions before adding the unique constraint
- [x] 1.4 Extend domain ports (`domain/ports.py`) with template, range-shift and request repository methods

## 2. Backend — generation & use cases

- [x] 2.1 Implement the generation service: materialize shifts from a template up to `today + 90d`, idempotent on `(employee, date)`, tracking `generated_through`
- [x] 2.2 Implement "extend +90" advancing `generated_through` and generating the next window
- [x] 2.3 Implement template regeneration that preserves rows where `status != scheduled` or `origin != template` and never touches past dates
- [x] 2.4 Implement coverage: mark absentee shift `day_off`, create substitute `covered` shift with `covered_by_employee_id`; implement availability query (template does not schedule weekday AND no shift on date)
- [x] 2.5 Implement time-off request use cases: create (pending), approve (→ day_off + optional coverage), reject (with reason); record `decided_by`/`decided_at`
- [x] 2.6 Extend `manage_staff.py` use cases for day-off / manual shift / range read wiring

## 3. Backend — repositories, API, schemas

- [x] 3.1 Implement repository methods (`infrastructure/repositories.py`) for templates, range shift query, requests, availability
- [x] 3.2 Add Pydantic schemas: template CRUD, request CRUD, coverage assignment, and additive `status`/`origin`/`covered_by_employee_id`/`note` on `PlannedShiftResponse`
- [x] 3.3 Add API routes: template CRUD + generate/extend, `GET /staff/shifts?branch_id&from&to`, day-off/coverage/manual shift actions, `time-off-requests` list + approve/reject; gate reads `staff.read`, writes `staff.manage`
- [x] 3.4 Backend tests (pytest): generation idempotency, regeneration preserves resolved slots, coverage audit trail, request approve/reject flows, range read scoping, duplicate-slot rejection, tenant/branch isolation
- [x] 3.5 `poetry run ruff check .` and `poetry run mypy src` clean

## 4. Seed & docs

- [x] 4.1 Extend `scripts/seed` and `scripts/seed_demo` to create demo templates and generate the 90-day horizon (idempotent)
- [x] 4.2 Add `docs/staff/` module docs for templates, shifts (status/coverage), and time-off requests

## 5. Frontend — service & store

- [x] 5.1 Extend `services/staff.api.ts`: template CRUD + generate/extend, `listShiftsRange`, day-off/coverage/manual actions, time-off request list/approve/reject; add `status`/`origin`/`covered_by`/`note` to `PlannedShift`
- [x] 5.2 Create a `shifts` Pinia store: week state, range fetch, cell resolution from real status, coverage/availability derivations, and mutation actions

## 6. Frontend — Phase 1: Calendario on real data

- [x] 6.1 Replace `ShiftsView.vue` in-memory seed with store-backed week data (range endpoint), resolving cells from real `status`; keep the El Pase model (mono role tag, coverage heat lamp)
- [x] 6.2 Wire calendar mutations to the API (create manual, mark day-off + optional coverage, assign coverage, edit hours, remove); gate by `staff.manage`
- [x] 6.3 Surface `generated_through` and warn when the visible week nears the horizon

## 7. Frontend — Phase 2: Solicitudes

- [x] 7.1 Build the Solicitudes inbox over `time-off-requests` (filter by status; approve with optional coverage; reject with reason)
- [x] 7.2 Reflect request decisions on the calendar; wire employee self-view "solicitar día libre" to create a pending request

## 8. Frontend — Phase 3: Plantillas

- [x] 8.1 Build the Plantillas editor (weekdays, entry/exit, validity) with live preview; save triggers regeneration; expose "extend +90 días"
- [x] 8.2 Frontend gates green: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`

## 9. Verification

- [x] 9.1 End-to-end against seeded demo data: author a template → generate → view week → mark día libre → assign coverage → submit & approve a request → extend horizon; confirm regeneration preserves resolved slots
