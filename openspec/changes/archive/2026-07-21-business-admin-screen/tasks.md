## 1. Backend — profile write

- [x] 1.1 Add repo writes: update tenant identity (name, tax_id, email, phone) and per-branch (address, phone), scoped by tenant
- [x] 1.2 `BusinessService.update_profile` with validation (non-empty name; branch belongs to tenant)
- [x] 1.3 `PUT /business/profile` (gate `menu.manage`) accepting tenant fields + a list of branch `{id, address, phone}`; returns the updated profile
- [x] 1.4 Tests: tenant + branch edit round-trip via the profile; unknown branch rejected; RBAC gate

## 2. Frontend — Perfil del negocio screen

- [x] 2.1 Reports/profile api: `getBusinessProfile`, `updateBusinessProfile`, `getBranchHours`, `setBranchHours`
- [x] 2.2 "Perfil del negocio" view: identity form (name/tax id/email/phone + logo preview), per-branch address/phone
- [x] 2.3 Weekly operating-hours editor per branch (per weekday: closed or open/close window), saving via the hours endpoint
- [x] 2.4 Staff roster reference (count/list from the profile), read-only
- [x] 2.5 Route + nav entry, gated `menu.manage`
- [x] 2.6 Frontend tests: profile load/edit round-trip; hours editor save

## 3. Validation

- [x] 3.1 Backend tests + ruff + mypy
- [x] 3.2 Frontend type-check, unit tests, lint, build
- [x] 3.3 `openspec validate business-admin-screen --strict` passes
