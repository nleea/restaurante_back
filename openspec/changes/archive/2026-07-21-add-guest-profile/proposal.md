## Why

Customers who order without creating an account currently retype their name, address, and phone on every visit — `front/src/stores/cart.ts` holds those fields only in memory and loses them on reset. A lightweight, cookie-backed guest profile lets returning anonymous customers see their checkout form pre-filled, reducing friction on the most common (no-login) path, without forcing account creation and without interfering with the existing real-user authentication.

## What Changes

- Introduce a `GuestProfile` record (UUID token, name, address, phone, timestamps, nullable `user_id`) persisted in PostgreSQL, keyed by an opaque token carried in a dedicated `guest_token` cookie — never the personal data itself.
- Add public (unauthenticated) endpoints to **create/update** (POST), **read from cookie** (GET, returns `null` cleanly when absent — never 500), and **edit** (PATCH) a guest profile.
- Set the `guest_token` cookie as `httponly`, `secure`, `samesite=lax`, `max_age=1 year`, with a name that does not collide with the real-user auth cookie/header.
- Add migration logic: when a guest with saved data registers or logs in, merge the `GuestProfile` into the real user account (copy contact fields / link via `user_id`).
- Ensure CORS uses `allow_credentials=True` with explicit origins (not `*`) so credentialed guest requests work alongside real auth.
- Frontend: the storefront checkout preloads the form from the guest profile on mount and persists edits via POST/PATCH with credentials included; when a real user is authenticated, their account data takes precedence over the guest profile.

## Capabilities

### New Capabilities
- `guest-profile`: anonymous, cookie-identified customer profile — persistence model, token/cookie lifecycle, public read/create/update endpoints, and guest→user merge on authentication.

### Modified Capabilities
- `frontend-storefront`: the customer checkout form preloads contact fields from the guest profile on mount, submits create/update on order, and defers to real-user account data when logged in.

## Impact

- **Backend**: new `guest_profile` module (domain/application/infrastructure per hexagonal convention), a new DB migration, router registration, and a review of CORS `allow_credentials`/origins and the auth dependency to guarantee coexistence with real auth.
- **Frontend**: `front/src/stores/cart.ts` (or a new guest-profile store/composable) plus the storefront checkout step; HTTP client must send credentials on guest calls without breaking real-auth credential handling.
- **Security**: cookie holds only the UUID; inputs validated via Pydantic; token is always read from the cookie (never query/body); an authenticated user must never read or overwrite another session's guest profile via precedence bugs.
- **No breaking changes** to existing auth or storefront ordering.
