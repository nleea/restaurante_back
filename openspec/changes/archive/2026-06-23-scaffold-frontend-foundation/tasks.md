# Tasks — scaffold-frontend-foundation

Build order is intentional: infra first, Login view last (you can only prove refresh once
you can log in and let a token expire). See `design.md` §Decision 8.

## 1. Toolchain & dev host
- [x] Add `axios`, `tailwindcss`, `primevue`, `tailwindcss-primeui` to `front/package.json`.
- [x] Wire Tailwind into Vite; register PrimeVue (styled mode) in `main.ts`; add the
      `tailwindcss-primeui` plugin so Tailwind utilities and PrimeVue's theme coexist.
- [x] Configure the Vite dev server to run at `demo.localhost` (`host:true` + `allowedHosts:['.localhost']`).
- [x] Smoke-check `GET http://demo.localhost:8000/health` (backend already runs locally). → 200 `{"status":"ok"}`
- [x] Update `front/CLAUDE.md` status (remove the stale "empty/not scaffolded" note).

## 2. Token storage leaf
- [x] `tokens.ts` with `get/set/clear` over `localStorage` (access + refresh).
- [x] No imports of the store or the Axios module (breaks the cycle).

## 3. Axios instance (no refresh yet)
- [x] `baseURL` derived from `window.location.hostname` (env-overridable, default `:8000`).
- [x] Request interceptor: attach `Authorization: Bearer <access>` when present.

## 4. Auth store (Pinia)
- [x] State: `accessToken, refreshToken, user, permissions[]`.
- [x] Getters: `isAuthenticated`, `can(code)`.
- [x] Actions: `login` (POST /auth/login → setTokens → fetchMe), `fetchMe` (GET /auth/me),
      `logout`, `bootstrap` (rehydrate from stored refresh token).

## 5. Refresh interceptor (single-flight)
- [x] On 401: first request triggers `POST /auth/refresh`; others subscribe to the in-flight
      promise (queue), then replay with the new token.
- [x] `/auth/refresh` bypasses this interceptor (uses bare `rawHttp`); retried requests flagged `_retry`.
- [x] On refresh failure: `tokens.clear()` + redirect to `/login?redirect=…`.
      (Refinement: uses `window.location.assign` instead of importing the router, to keep the
      `http → router → store → http` graph acyclic — see note in "Deviations" below.)

## 6. Router guards
- [x] `beforeEach`: `meta.requiresAuth` → redirect if not authenticated.
- [x] Hydrate via `await bootstrap()` when a token exists but the store is empty (F5 race).
- [x] `meta.permission` → `/403` when `!can(perm)`.

## 7. Minimal Login view + end-to-end proof
- [x] Login form (PrimeVue) → `auth.login` → redirect to a guarded placeholder route gated
      by `rbac.manage` (the slot the next change turns into the RBAC/users screen).
- [x] Prove against the running backend (`admin@demo.com` / `admin1234`): login → `/auth/me`
      (33 perms incl. `rbac.manage`) → `/auth/refresh` rotates → unauthenticated `/auth/me`
      returns 401. Single-flight refresh + `_retry` loop-prevention covered by unit tests.

## 8. Tests
- [x] Unit: refresh single-flight queues concurrent 401s into one refresh; `_retry` prevents
      loops; `can()` reflects `/auth/me` permissions. (5 tests pass.)
- [ ] (Optional) Cypress e2e: login → guarded route → logout. — deferred; not required for the
      foundation. The unit + API-level proofs cover the contract.

## Backend addition required for the foundation to work in-browser (recorded)
- **CORS was missing on the backend.** With front at `demo.localhost:5173` and API at
  `demo.localhost:8000` (different port = different origin), the browser sends a preflight
  `OPTIONS` that got no CORS headers, so the real `POST /auth/login` was blocked (only the
  `OPTIONS` reached the API). Fix: added `CORSMiddleware` in `backend/.../main.py` with a
  configurable `cors_allow_origin_regex` setting (default matches any `*.localhost:<port>`),
  added **after** `TenantResolverMiddleware` so CORS is the outermost layer and answers the
  preflight before tenant logic. Verified: preflight → 200 with `access-control-allow-*`;
  real POST carries `access-control-allow-origin`; backend suite still green (155 passed).
  This was outside the original frontend-only scope but is required for the layer to function.

## Deviations from design (recorded)
- **Decision 5 logout mechanism:** the design said the interceptor would `router.push`. Because
  `router → store → http`, importing the router into `http.ts` would create a cycle. Resolved
  by using `window.location.assign('/login?redirect=…')` (a hard nav, which also clears app
  state on logout). Honors the *spirit* of Decisions 2/5 (acyclic graph); the auth store still
  exposes `logout()` for UI-initiated logout.
