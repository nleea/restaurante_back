## Why

The `front/` Vue scaffold exists but has no application infrastructure: no HTTP layer, no
auth, no route protection, and it's missing the two dependencies the backend integration
contract requires (Axios, Tailwind). No business screen can be built reliably until the
foundation — tenant-aware HTTP, transparent JWT refresh, an identity/permissions store, and
permission-gated routing — exists and is proven against the live backend. This change builds
exactly that foundation and stops before any business screen.

## What Changes

- Add `axios`, `tailwindcss`, and `primevue` (+ `tailwindcss-primeui`) to the toolchain;
  wire Tailwind and PrimeVue into Vite (PrimeVue for components, Tailwind for layout).
- Run the dev server at `demo.localhost` so the **Host-subdomain tenant** contract holds.
- Add a single Axios instance with a `baseURL` derived from the browser Host, a request
  interceptor that attaches `Authorization: Bearer`, and a response interceptor doing
  **single-flight transparent refresh** on 401 with a request queue.
- Add `tokens.ts` (storage leaf that breaks the `axios ↔ store` cycle).
- Add a Pinia `auth` store: `login`, `logout`, `fetchMe`, `bootstrap`, `can(code)`.
- Add router guards gating by `meta.requiresAuth` and `meta.permission`, surviving F5 via
  `bootstrap()`.
- Add a minimal Login view to prove the foundation end-to-end.
- Refresh the stale `front/CLAUDE.md` status note.

## Impact

- Affected: `front/` only (`package.json`, `vite.config.ts`, new `src/lib|services|stores`,
  `src/router`, a Login view, `front/CLAUDE.md`). No backend changes.
- Unblocks: every subsequent per-module screen reuses this HTTP + auth + RBAC layer. The
  **RBAC/users management screen** is the planned next change and first consumer.
- Design and decisions: see `design.md`. Non-goals: business screens, `v-can` directive,
  prod host mapping, storage hardening — all deferred.
