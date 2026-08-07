## 1. Backend — structured hours

- [x] 1.1 Model per-branch operating hours (weekday + open/close minutes, closed day, midnight-crossing); migration `0020` + register in models_registry/env
- [x] 1.2 Helpers: "is open at time T" and "next opening from T" (handle overnight + closed days)
- [x] 1.3 Tests for the hours helpers (normal, overnight, all-closed, wrap-around, boundary)

## 2. Backend — business profile

- [x] 2.1 Business-profile read aggregating tenant identity + branch details + hours + staff count
- [~] 2.2 Business-profile update — HOURS write done (`PUT /business/branches/{id}/hours`). DEFERRED: writing tenant/branch identity fields (no existing tenant/branch edit endpoints; own change)
- [ ] 2.3 DEFERRED: single-source name/photo — storefront still reads name/logo from the appearance JSON. The profile READ exposes the same values; deep rewiring of the storefront read path is deferred (invasive, see design)
- [~] 2.4 Tests: profile read + hours CRUD/validation done. DEFERRED: identity-write + name/photo-reflected tests (with 2.2/2.3)

## 3. Backend — storefront

- [x] 3.1 Storefront exposes structured hours + computed next opening (`GET /storefront/hours`, public)
- [ ] 3.2 DEFERRED: storefront identity (name/photo) sourced from the profile (see 2.3)
- [x] 3.3 Tests: closed state carries next opening; open-all-week; empty when no hours

## 4. Frontend

- [ ] 4.1 DEFERRED: "Perfil del negocio" admin screen (identity + branch details + hours editor + staff reference). Backend endpoints exist and are tested; the admin editing UI is a follow-on
- [x] 4.2 Storefront closed state: "cerrado · abrimos a las X" from the hours (enriches the cash-session-operating-shift closed message)
- [~] 4.3 Frontend tests: api-layer test for `getStorefrontHours` done. DEFERRED: the Perfil screen tests (with 4.1)

## 5. Validation

- [x] 5.1 Backend tests + ruff + mypy; alembic 0020 up/down on Postgres
- [x] 5.2 Frontend type-check, unit tests, lint, build
- [x] 5.3 `openspec validate business-profile-and-hours --strict` passes

## Deferred → follow-up change (recommended)

The business identity **write + Perfil del negocio admin screen + deep identity unification**
(2.2 identity, 2.3, 3.2, 4.1) form a coherent second slice. The foundation shipped here
(structured hours end-to-end + profile read + storefront "abrimos a las X") unblocks them.
