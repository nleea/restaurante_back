## Context

The `front/` directory holds a default `npm create vue` scaffold (Vue 3.5 + Vite + Pinia
+ Vue Router + TS + Vitest + Cypress). The router has `routes: []`, `App.vue` is the
placeholder, and the only store is the example `counter`. The two dependencies the
integration contract actually requires — **Axios** and **Tailwind CSS** — are not yet in
`package.json`. (`front/CLAUDE.md` is stale: it claims the directory is empty/not
scaffolded.)

This change designs the **foundation layer**: the client-side infrastructure every future
screen reuses. It deliberately stops before any business screen. The load-bearing
knowledge is the backend integration contract (`front/CLAUDE.md` §"Backend integration
contract"):

- **Tenant is resolved by Host subdomain**, not a body field. Dev API host is
  `http://<slug>.localhost:8000` (e.g. `demo.localhost:8000`); `*.localhost` resolves to
  `127.0.0.1` without `/etc/hosts`. Wrong host → wrong/no tenant. This is the #1 mistake.
- **Auth is JWT access + refresh.** `POST /auth/login {email,password}` →
  `{access_token, refresh_token, token_type}`. Access expires in **15 min**, refresh in
  **7 days**. `POST /auth/refresh {refresh_token}` → new pair. Transparent refresh on 401
  is required.
- **The JWT does not carry permissions.** `GET /auth/me` (Bearer) →
  `{id, email, name, permissions: string[]}`, resolved server-side per request.
- **RBAC gates the UI** by `"<module>.<action>"` codes (e.g. `menu.read`, `menu.manage`).
  Frontend gating is **UX, not security** — the backend enforces independently.
- **`branch_id` from day one**, even with a single branch today.

Facts confirmed in the scaffold:
- `main.ts` already wires Pinia + Router; alias `@ → src` exists in `vite.config.ts`.
- No Axios, no Tailwind, no HTTP layer, no auth store, no guards yet.

## Goals / Non-Goals

**Goals:**
- A single Axios instance whose `baseURL` carries the tenant via the Host subdomain.
- Transparent refresh-on-401 with **single-flight** refresh and a request queue.
- A token storage module that breaks the `axios ↔ store` import cycle.
- A Pinia `auth` store: `login`, `logout`, `fetchMe`, `bootstrap`, `can(code)`.
- Router guards that gate by `meta.requiresAuth` and `meta.permission`, surviving F5.
- Dev server running at `demo.localhost` so the subdomain contract holds end-to-end.
- Axios + Tailwind + **PrimeVue** added to the toolchain (PrimeVue for components,
  Tailwind for layout/utilities).

**Non-Goals (deferred):**
- Any business screen (menu, inventory, orders, …) — separate change(s). The **RBAC/users
  management screen** is the planned next change and the first consumer of this layer.
- A component-level permission directive (`v-can`) beyond the route guard — fast follow.
- Production host/slug mapping implementation (documented as a decision, not built).
- i18n, theming, design system, error-toast UX polish.
- SSR. This is a SPA client for an existing API.

## Decisions

**1. `baseURL` is derived from the browser Host, not hard-coded.**
`baseURL = \`${protocol}//${window.location.hostname}:8000\`` in dev (configurable via an
env var with that default). Because the dev server runs at `demo.localhost`, the tenant
slug rides along automatically and there is no `tenant_id` anywhere in the client.
Rationale: the contract makes the Host authoritative; deriving from it makes the #1
integration mistake unrepresentable. Trade-off: front and API must share the subdomain
shape (see Decision 6 / Open Questions for prod).

**2. Tokens live in a standalone `tokens.ts`, not in the store or the Axios module.**
Plain `get/set/clear` functions over storage. Both the Axios interceptors and the auth
store import *this*, never each other. Rationale: the interceptor needs the access token
to set `Authorization`, and the store needs to persist tokens after login; if the
interceptor imported the store (which imports Axios) we'd get a circular dependency. A
neutral leaf module is the standard break.

**3. Storage strategy: both tokens in `localStorage` initially, taken consciously.**
The backend returns tokens in the JSON body (no httpOnly cookies), so the client must
store them. For an internal B2B SaaS with a 15-min access token, `localStorage` for both
is the pragmatic start; the alternative (access in memory, refresh in `localStorage`)
halves the XSS surface but adds rehydration complexity. Rationale: ship the simple version,
record the trade-off, revisit when hardening. This is an explicit decision, not a default.

**4. Refresh is single-flight with a subscriber queue.**
On a 401, the response interceptor checks an `isRefreshing` flag/promise. The **first** 401
triggers `POST /auth/refresh` and stores the in-flight promise; **subsequent** 401s
subscribe to that same promise instead of firing their own. On success, all queued requests
replay with the new access token; on failure, all reject and the client logs out.
Guards against the two classic bugs:
- Each retried request is marked `_retry` — a second 401 on an already-retried request does
  **not** loop; it goes to logout.
- The `/auth/refresh` call itself **bypasses** this interceptor (no self-trigger).
Rationale: N requests expiring together must rotate the refresh token exactly once; parallel
refreshes race and invalidate each other.

**5. Logout from the interceptor avoids re-importing the store.**
On unrecoverable auth failure the interceptor calls `tokens.clear()` and
`router.push('/login?redirect=…')` directly (router import creates no cycle), rather than
importing the auth store. The store also exposes `logout()` for UI-initiated logout; both
funnel through `tokens.clear()`. Rationale: keep the dependency graph acyclic; one source of
truth for "tokens gone".

**6. `auth` store is the single source of identity + permissions; `can()` is the gate.**
State: `accessToken, refreshToken, user, permissions[]`. Getters: `isAuthenticated`,
`can(code) → permissions.includes(code)`. Actions: `login → POST /auth/login → setTokens →
fetchMe`; `fetchMe → GET /auth/me`; `bootstrap()` rehydrates `user`/`permissions` from a
stored refresh token before the first route resolves; `logout()`. Rationale: permissions
come only from `/auth/me`, so the store must own them and the UI must read `can()` — never
decode the JWT for permissions.

**7. Guards handle the F5 race via `bootstrap()`.**
`router.beforeEach`: (1) if `meta.requiresAuth` and not authenticated → `/login?redirect`;
(2) if a token exists but the store isn't hydrated yet → `await bootstrap()` before
deciding; (3) if `meta.permission` and `!can(perm)` → `/403`. Rationale: after a refresh,
the token is in storage but the store is empty; without the hydrate step a logged-in user
gets bounced to login.

**8. Build order: infra first, Login screen last.**
`tokens.ts → axios (no refresh) → auth store (login/fetchMe) → refresh interceptor →
guards → bootstrap() → Login view`. Rationale: you can only prove the refresh interceptor
works once you can log in and let an access token expire; building it first is untestable.

**9. PrimeVue for components, Tailwind for layout — they coexist.**
PrimeVue (DataTable, forms, dialogs, calendars) covers the heavy CRUD surface a back-office
needs out of the box; Tailwind handles layout, spacing, and one-off utilities. They
integrate cleanly (PrimeVue styled mode + the `tailwindcss-primeui` plugin so Tailwind
utilities don't fight PrimeVue's theme). Rationale: this product is form/table-heavy
(RBAC, menu, inventory, finance); building those primitives by hand would be the bulk of
the work for little gain. Trade-off: less pixel-level control and an extra dependency,
accepted for delivery speed.

**10. The Login proof routes to a guarded placeholder that becomes the RBAC screen.**
The end-to-end proof (Decision 8) lands on a guarded route gated by a real permission
(`rbac.manage`), which the **next** change turns into the RBAC/users management screen.
Rationale: RBAC is the natural first business screen after auth and exercises `can()` +
route/permission gating hardest, so the foundation is validated against the exact pattern
its first consumer needs. RBAC itself is out of scope here (see Non-Goals).

## Risks / Trade-offs

- **`localStorage` tokens are XSS-readable** → accepted for v1 (internal SaaS, short access
  TTL); documented for hardening. Mitigation path: move access token to memory.
- **Subdomain coupling in prod** → deriving the API host from the front Host assumes they
  share the subdomain shape. If prod splits `app.demo.com` / `api.demo.com`, the derivation
  needs a mapping. Surfaced as an Open Question; dev is unaffected.
- **`demo.localhost` dev setup friction** → some tooling/browsers need the dev server bound
  to `demo.localhost`. Documented in tasks; `*.localhost` avoids `/etc/hosts` edits.
- **Refresh-storm edge cases** (clock skew, refresh token already rotated by another tab) →
  single-flight handles same-tab; cross-tab can still double-refresh. Acceptable for v1;
  a `storage`-event sync is a fast follow if it bites.
- **Frontend gate is UX only** → never rely on `can()` for security; the backend enforces.
  Documented so future screens don't treat hidden = forbidden.

## Migration Plan

Greenfield client — no data migration. Sequenced, each step independently runnable:
1. Add deps: `axios`, `tailwindcss` (+ Tailwind/Vite wiring). Refresh `front/CLAUDE.md`
   status (it wrongly says "empty").
2. Configure dev server host = `demo.localhost`; verify `GET http://demo.localhost:8000/health`.
3. Land `tokens.ts`, the Axios instance, the auth store, the refresh interceptor, guards,
   `bootstrap()`, then a minimal Login view — in that order.
4. Prove end-to-end against the seeded backend (`admin@demo.com` / `admin1234`): login →
   `/auth/me` → a guarded placeholder route → force token expiry → observe one transparent
   refresh → logout.

## Open Questions

- **Prod slug↔host mapping** — front under `<slug>.<domain>` with a derived API host, or a
  configured API base per environment? (Default: keep the subdomain shape in prod and derive,
  to preserve the contract; decide before first deploy.)
- **Storage hardening now or later?** — ship `localStorage`-both now, or start with
  access-in-memory? (Default: `localStorage` both for v1, revisit at hardening.)
- **Component-level gating** — add a `v-can` directive in this change or the next? (Default:
  route guard only here; directive as a fast follow when the first screen needs to hide a
  button.)
- **Cross-tab refresh sync** — add a `storage`-event listener to share the new token pair
  across tabs now, or defer? (Default: defer; single-flight covers the common case.)
