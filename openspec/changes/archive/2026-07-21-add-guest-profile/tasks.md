## 1. Confirm open questions before coding

- [x] 1.1 Inspect the real-user contact model (`modules/customers` `CustomerModel`/`person` and the `users` table) to decide the merge target for `claim` (copy fields vs link `user_id`) — DECISION: link via `user_id` (identity lives in `person` via `Customer`; link is the safe non-destructive default per design open question)
- [x] 1.2 Confirm `GuestProfile` scoping (tenant-only vs branch) against how storefront orders resolve a branch — DECISION: tenant-only (`TenantScopedMixin`); storefront resolves branch internally, uses `TenantDep` only
- [x] 1.3 Add/confirm a settings flag for the environment-conditional `secure` cookie attribute (prod=True, dev=False) — DECISION: reuse existing `settings.debug` → `secure = not debug`; no new setting

## 2. Backend — domain & application

- [x] 2.1 Create module skeleton `modules/guest_profile/` (`domain/`, `application/`, `infrastructure/`) mirroring the `customers` module
- [x] 2.2 Add `GuestProfile` domain dataclass (`domain/entities.py`): token, name, address, phone, timestamps, nullable user_id
- [x] 2.3 Define repository port(s) in `domain/ports.py` (get by tenant+token, upsert, patch, link user)
- [x] 2.4 Implement `manage_guest_profile` use cases (`application/use_cases/`): create-or-update, read-by-token, patch, claim/merge

## 3. Backend — infrastructure & persistence

- [x] 3.1 Add `GuestProfileModel` (`infrastructure/models.py`) with `TenantScopedMixin` + `TimestampMixin`, UUID `id`, unique+indexed `token`, nullable `user_id` FK→users, table `guest_profiles` (English)
- [x] 3.2 Implement repository (`infrastructure/repositories.py`) against the domain ports
- [x] 3.3 Register the model in `migrations/env.py` (via `shared/models_registry` import) and `shared/models_registry`
- [x] 3.4 Generate Alembic migration `0018_guest_profile` (create table + unique index on `token`)

## 4. Backend — API

- [x] 4.1 Add camelCase Pydantic schemas (`infrastructure/api/schemas.py`): `_CamelModel`, `GuestProfileWrite`, null-friendly `GuestProfileRead`
- [x] 4.2 Implement router (`infrastructure/api/router.py`, prefix `/guest-profile`, `TenantDep`): POST create/update setting `guest_token` cookie (httponly, samesite=lax, max_age=1yr, env-conditional secure); GET read-from-cookie returning null cleanly (never 500); PATCH edit
- [x] 4.3 Add authenticated `POST /guest-profile/claim` (`CurrentUserDep`) that merges the cookie's guest profile into the user account and clears the cookie
- [x] 4.4 Ensure GET/PATCH read the token ONLY from the cookie (never query/body); reject/ignore token supplied elsewhere
- [x] 4.5 Wire `include_router` into `main.py`; confirm CORS `allow_origin_regex` covers storefront hosts (no `*`)

## 5. Backend — tests

- [x] 5.1 Test create issues cookie + row; update reuses the same token (no duplicate)
- [x] 5.2 Test GET returns null (200) with no cookie and with an unknown token; never 500
- [x] 5.3 Test PATCH edits only provided fields; token sourced only from cookie
- [x] 5.4 Test `claim` merges into the authenticated user and cannot read another session's profile; JWT auth still works alongside the guest cookie

## 6. Frontend

- [x] 6.1 Add a guest-profile service using the shared axios instance with per-request `{ withCredentials: true }` (GET/POST); do NOT flip `withCredentials` globally
- [x] 6.2 Add `useGuestProfileStore`: GET on checkout mount; when `!authStore.isAuthenticated` and data exists, hydrate `cart.ts` (`customerName`/`customerPhone`; address → `reference`, see store note on structured-address mismatch)
- [x] 6.3 On order confirm in `StorefrontView`, POST the entered contact data to persist the guest profile (non-blocking)
- [x] 6.4 When `authStore.isAuthenticated`, do NOT read or override from the guest profile (account data wins)
- [x] 6.5 Frontend tests: prefilled form for returning guest; empty form + no error for first-time guest; failed fetch swallowed; logged-in precedence (read + write)

## 7. Validation

- [x] 7.1 Run backend tests + lint; run Alembic migration up/down locally — 480 passed; ruff+mypy clean on module; alembic 0018→0017→0018 round-trip clean on Postgres
- [x] 7.2 Run frontend type-check, unit tests, lint, and production build — type-check clean, 345 passed, lint clean, build ok
- [x] 7.3 `openspec validate add-guest-profile --strict` passes
