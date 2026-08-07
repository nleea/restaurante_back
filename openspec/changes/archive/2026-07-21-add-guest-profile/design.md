## Context

The storefront (`/store`) lets anonymous customers order without an account. Their contact data (`customerName`, `customerPhone`, `address`, `gps`) lives only in `front/src/stores/cart.ts` and is lost on reset — returning guests retype everything. We want a cookie-backed, DB-persisted guest profile that pre-fills the checkout, running in parallel with the real-user auth without interfering with it.

Reconnaissance of the current system (authoritative constraints for this design):

- **Auth is JWT via the `Authorization: Bearer` header — no cookies anywhere backend-side** (`shared/security/jwt.py`, `modules/identity/infrastructure/api/deps.py`). A `guest_token` cookie therefore has **zero collision risk** with auth. Frontend token storage is localStorage (`auth.access_token`), not cookies.
- **CORS already sets `allow_credentials=True`** with `allow_origin_regex` (not `*`) in `main.py:80-86`, so a credentialed cookie flow is already compatible; no CORS change is required beyond confirming the origin regex covers storefront hosts.
- **Model convention**: `Base(DeclarativeBase)` + `TimestampMixin` + `TenantScopedMixin`/`BranchScopedMixin` (`shared/database.py`); `id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)`; English table names; hexagonal layering `API → application → domain`, infra implements domain ports.
- **Migrations**: Alembic under `backend/migrations/versions/`; latest numbered is `0017_order_payment_method.py`; new models must be registered in `migrations/env.py` and `shared/models_registry`.
- **Routers**: direct `app.include_router(...)` in `main.py` (no aggregator); module exports `router` from `infrastructure/api/router.py`.
- **Schemas**: per-module `_CamelModel` with `ConfigDict(alias_generator=to_camel, populate_by_name=True)` — camelCase wire contract.
- **Frontend HTTP**: single axios instance `front/src/lib/http.ts` attaches Bearer in an interceptor and does **not** set `withCredentials`. `useAuthStore.isAuthenticated` is the logged-in signal. Checkout POST currently happens in `StorefrontView`, not the store.

## Goals / Non-Goals

**Goals:**
- Persist an anonymous guest profile keyed by an opaque `guest_token` cookie, coexisting cleanly with JWT auth.
- Public GET/POST/PATCH endpoints for read/create/update, plus an authenticated merge path for guest→user transition.
- Pre-fill the storefront checkout from the guest profile on mount; defer to real-user account data when logged in.

**Non-Goals:**
- No change to the real-user auth mechanism (still Bearer/JWT).
- No account creation, password, or session for guests — only a token.
- No storefront ordering/flow redesign; this only hydrates/persists contact fields.
- No rate-limiting/abuse hardening of public endpoints (tracked separately; the storefront router already flags it).

## Decisions

**1. New backend module `guest_profile` (hexagonal), tenant-scoped.**
Follow the `customers` module layout: `domain/{entities,ports}.py`, `application/use_cases/manage_guest_profile.py`, `infrastructure/{models,repositories,api/{router,schemas,deps}}.py`. `GuestProfileModel` uses `TenantScopedMixin` + `TimestampMixin`, columns: `id` (UUID pk), `token` (UUID, **unique + indexed**), `name`, `address`, `phone` (nullable strings), `user_id` (nullable FK→users). Tenant scoping means the profile is resolved by `(tenant_id from subdomain, token from cookie)`, adding defense against cross-tenant token reuse.
*Alternative considered:* extend the `customers` module. Rejected — a guest is not a `Customer`/`person`; a separate table keeps the anonymous lifecycle isolated and the merge explicit.

**2. Cookie `guest_token`: opaque UUID only, `httponly`, `samesite=lax`, `max_age=1yr`; `secure` is environment-driven.**
The cookie never carries personal data — only the token. `secure=True` in production, but must be **conditional on environment** (a settings flag) so local `http://…:dev` can still set the cookie. Name `guest_token` — chosen to avoid the `auth.*` frontend keys for clarity even though there is no technical collision.
*Alternative considered:* always `secure=True`. Rejected — breaks local dev over http.

**3. Token is read only from the cookie; server generates it.**
POST creates the row and issues the cookie when absent, or updates the row for the cookie's token. GET/PATCH resolve the profile solely from the cookie — never query/body — and GET returns a clean `null` (200) when the cookie or row is missing, never 500.

**4. Merge is an explicit authenticated endpoint, not a login hook.**
Add `POST /guest-profile/claim` gated by `CurrentUserDep` that reads the `guest_token` cookie, copies the guest's contact fields onto the authenticated user's customer/person record (and/or sets `GuestProfile.user_id`), then may clear the guest cookie. Keeping merge out of the identity module avoids coupling and keeps auth untouched.
*Alternative considered:* hook merge into the login use case. Rejected — couples two modules and runs on every login even when no guest cookie exists.

**5. Frontend: `withCredentials` only on guest-profile calls; a small Pinia store/composable hydrates `cart.ts`.**
Do **not** flip `withCredentials` globally on the shared `http` instance. Instead the guest-profile service passes `{ withCredentials: true }` per request (needed on both the cookie-setting POST and the reading GET). A `useGuestProfileStore` (or composable) calls GET on checkout mount and, when `!authStore.isAuthenticated` and data exists, hydrates `customerName`/`customerPhone`/`address` in `cart.ts`; on order confirm it POSTs/PATCHes the entered data. When `authStore.isAuthenticated`, account data wins and the guest GET is not applied.
*Alternative considered:* global `withCredentials`. Rejected — unnecessary blast radius on every authenticated Bearer request.

**6. Reuse the camelCase schema convention.**
Define a module-local `_CamelModel` (mirroring storefront/customers) for `GuestProfileRead`/`GuestProfileWrite`; GET returns `null`-friendly optional payload.

## Risks / Trade-offs

- **`secure=True` cookie not set over http in dev** → Mitigation: environment-conditional `secure` flag from settings; document that guests only persist over https in prod (expected).
- **Merge target ambiguity** (how a real user stores contact data — via `CustomerModel`/`person`) → Mitigation: confirm the exact User→Customer/person shape at implementation time (see Open Questions); default to setting `user_id` + copying fields onto the user's customer record if present.
- **Cross-session precedence bug** (authenticated user reads/overwrites a stranger's guest profile) → Mitigation: guest endpoints never consult auth identity; precedence is enforced in the frontend by checking `isAuthenticated` before applying the guest GET; merge is explicit and user-scoped.
- **Public unauthenticated write endpoints invite abuse** → Mitigation: out of scope here, but note tenant-scoping and flag rate-limiting as a fast-follow (consistent with the storefront order router's existing note).
- **`samesite=lax` with cross-subdomain storefront** → Mitigation: storefront is served on the tenant subdomain (same site as the API host), so `lax` is sufficient; revisit if the storefront ever moves to a third-party origin.

## Migration Plan

1. Add `GuestProfileModel`; generate Alembic migration `0018_guest_profile` (table `guest_profiles`, unique index on `token`, nullable `user_id` FK); register model in `migrations/env.py` and `shared/models_registry`.
2. Wire the router into `main.py` (`app.include_router`), public prefix `/guest-profile`.
3. Ship backend; endpoints are additive — no existing behavior changes, safe rollback by dropping the router include and the table.
4. Add frontend store/service and hydrate checkout; guarded by `isAuthenticated` so logged-in users are unaffected.

## Open Questions

- What is the canonical place a **real user's** contact data lives (`CustomerModel` fields vs a linked `person`)? Confirm before writing the `claim` merge so it targets the right record.
- Should `GuestProfile` be **tenant-scoped only** or also **branch-scoped**? Default: tenant-scoped (a guest belongs to a restaurant, not a branch) — confirm against how storefront orders pick a branch.
- On successful `claim`, do we **delete** the guest profile and clear the cookie, or keep it linked via `user_id`? Default: clear the cookie, keep the row linked for audit.
