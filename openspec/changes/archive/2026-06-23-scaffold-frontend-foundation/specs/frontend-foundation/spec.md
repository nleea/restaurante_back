## ADDED Requirements

### Requirement: Tenant-aware HTTP client

The frontend SHALL route all backend calls through a single Axios instance whose `baseURL`
carries the tenant via the Host subdomain (e.g. `http://demo.localhost:8000`), derived from
the browser host in development. The client SHALL NOT include any `tenant_id` in request
bodies.

#### Scenario: Tenant rides on the Host subdomain
- **WHEN** the app runs at `demo.localhost` and issues an API request
- **THEN** the request targets `demo.localhost:8000` so the backend resolves tenant `demo`
- **AND** no `tenant_id` field is present in the request body

#### Scenario: Access token is attached when present
- **WHEN** an authenticated request is issued and an access token is stored
- **THEN** the client sends `Authorization: Bearer <access_token>`

### Requirement: Transparent token refresh on 401

The client SHALL transparently refresh the access token on a `401` using
`POST /auth/refresh`, with a single in-flight refresh shared by all concurrent failures, and
SHALL replay queued requests with the new token. On refresh failure the client SHALL clear
tokens and redirect to login.

#### Scenario: Concurrent 401s trigger exactly one refresh
- **WHEN** several requests receive `401` at nearly the same time
- **THEN** only one `POST /auth/refresh` is issued
- **AND** the other requests wait for it and replay with the new access token

#### Scenario: Refresh call does not loop
- **WHEN** a request that was already retried after refresh receives `401` again
- **THEN** the client does not retry again and proceeds to log out
- **AND** the `POST /auth/refresh` request itself bypasses the refresh interceptor

#### Scenario: Refresh failure logs out
- **WHEN** `POST /auth/refresh` fails
- **THEN** stored tokens are cleared
- **AND** the user is redirected to `/login` preserving the intended destination

### Requirement: Identity and permission store

The frontend SHALL maintain an auth store that owns the access token, refresh token, current
user, and the permission codes returned by `GET /auth/me`. It SHALL expose `login`, `logout`,
`fetchMe`, `bootstrap`, and a `can(code)` check. Permissions SHALL come only from
`/auth/me`, never decoded from the JWT.

#### Scenario: Login resolves identity and permissions
- **WHEN** a user logs in with valid credentials
- **THEN** the token pair is stored
- **AND** `GET /auth/me` populates the user and permission codes

#### Scenario: Permission check reflects /auth/me
- **WHEN** `can('menu.read')` is evaluated
- **THEN** it returns true only if `menu.read` is in the permissions from `/auth/me`

#### Scenario: Session rehydrates after reload
- **WHEN** the page is reloaded while a refresh token is stored
- **THEN** `bootstrap()` restores the user and permissions before the first route resolves

### Requirement: Permission-gated routing

The router SHALL gate navigation: routes marked `requiresAuth` redirect unauthenticated
users to `/login`, and routes declaring a `permission` redirect users lacking that code to a
forbidden view. This gating is UX only; the backend remains the authority.

#### Scenario: Unauthenticated access is redirected
- **WHEN** an unauthenticated user navigates to a route marked `requiresAuth`
- **THEN** they are redirected to `/login` with the intended destination preserved

#### Scenario: Missing permission is forbidden
- **WHEN** an authenticated user navigates to a route requiring `menu.manage` and they lack it
- **THEN** they are redirected to a forbidden (`/403`) view

#### Scenario: Authenticated reload preserves access
- **WHEN** an authenticated user reloads on a guarded route
- **THEN** after `bootstrap()` they remain on the route without being bounced to login
