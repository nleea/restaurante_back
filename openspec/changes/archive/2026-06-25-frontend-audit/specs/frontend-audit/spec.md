## ADDED Requirements

### Requirement: Audit service layer

The Audit API service SHALL expose typed functions covering the `/audit` read endpoints: list audit
entries (`GET /audit/logs`, with optional `action`, `actor_id`, `entity_type`, `entity_id`,
`branch_id` filters and `limit`/`offset` pagination) and get a single entry by id
(`GET /audit/logs/{id}`). The service SHALL omit filter params that are not set rather than send
empty values.

#### Scenario: List with filters and pagination

- **WHEN** `listLogs({ action: 'login', limit: 50, offset: 0 })` is called
- **THEN** it GETs `/audit/logs` passing `action=login`, `limit=50`, `offset=0` and resolves with the
  array of `AuditLog`

#### Scenario: Unset filters are omitted

- **WHEN** `listLogs({ limit: 50, offset: 0 })` is called with no `action`/`actor_id`/etc.
- **THEN** the request includes only `limit` and `offset` — no empty filter params

#### Scenario: Get one entry

- **WHEN** `getLog(id)` is called
- **THEN** it GETs `/audit/logs/{id}` and resolves with the `AuditLog`

### Requirement: Audit store with offset pagination

The Audit store SHALL hold the loaded entries (newest-first), the active filters, and the pagination
offset, loading the first page on query and appending subsequent pages on load-more. Because the
endpoint returns a plain list with no total, the store SHALL infer whether more entries may exist
from whether the last page was full (returned `limit` rows), and SHALL expose that as a
`reachedEnd` signal.

#### Scenario: Query loads the first page

- **WHEN** the store queries with a set of filters
- **THEN** `entries` holds the first page newest-first and the offset is reset

#### Scenario: Load more appends the next page

- **WHEN** the user loads more and the previous page was full
- **THEN** the store fetches the next offset and appends the results

#### Scenario: Reached end when a short page returns

- **WHEN** a page returns fewer than `limit` entries
- **THEN** the store marks `reachedEnd` so no further load-more is offered

### Requirement: Best-effort actor name resolution

The store SHALL resolve an entry's `actor_id` to a user name when the current user also holds
`rbac.manage` (loading the users directory from `/rbac/users`), and SHALL degrade gracefully to a
short id reference when the directory is unavailable or the actor is null.

#### Scenario: Actor resolves to a name

- **WHEN** the actor directory is available and an entry's `actor_id` maps to a known user
- **THEN** the entry shows that user's name

#### Scenario: Actor degrades without the directory

- **WHEN** the user lacks `rbac.manage` (no directory) or the actor cannot be resolved
- **THEN** the entry shows a short actor reference (or "sistema" when `actor_id` is null)

### Requirement: Audit log viewer

The AuditView SHALL list the tenant's audit entries newest-first, each showing the action, actor,
entity (type and short id), and timestamp, with filters for action (exact value or dotted prefix),
entity type, and actor, plus an optional active-branch filter, and a load-more control; selecting an
entry SHALL show its full detail (action, actor, entity type + id, branch, IP, the free-form detail
text, and timestamp). The screen SHALL be read-only — no mutation controls.

#### Scenario: View recent entries

- **WHEN** an authorized user opens the screen
- **THEN** the tenant's entries are listed newest-first

#### Scenario: Filter by action prefix

- **WHEN** the user filters by action `login`
- **THEN** only entries whose action matches that value or dotted prefix (e.g. `login.success`,
  `login.failure`) are shown

#### Scenario: Inspect an entry

- **WHEN** the user selects an entry
- **THEN** its full detail is shown, including IP, the detail text, and the timestamp

### Requirement: Permission gating and navigation

The Audit screen SHALL be reachable at `/audit` only for authenticated users with `audit.read`,
exposed via a navigation entry. This gating is UX — the backend enforces authorization
independently.

#### Scenario: Route guarded by permission

- **WHEN** a user without `audit.read` navigates to `/audit`
- **THEN** the router redirects them to the forbidden view

#### Scenario: No write affordances

- **WHEN** any user views the screen
- **THEN** only read and filter controls are present — there are no create/edit/delete actions
