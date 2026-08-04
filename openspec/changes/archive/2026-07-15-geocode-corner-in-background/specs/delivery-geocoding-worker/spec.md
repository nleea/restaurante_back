## ADDED Requirements

### Requirement: Resolve delivery pins outside the request path

The system SHALL resolve delivery pins in the background, so that taking an order never waits
on a geocoding provider. Providers answer in seconds and fail intermittently — measured at
1.6–9.1 s with one request in three returning 504 — which is tolerable only where nobody is
waiting.

The set of work SHALL be derived from the delivery records themselves — a record that has an
address and no location needs a pin — rather than from a message queue. State lives in the row,
so the work is idempotent, survives a restart, and retries by simply remaining unresolved.

Records already carrying a location SHALL NOT be re-resolved, including hand-placed pins.

#### Scenario: A new delivery gets its pin without blocking the order

- **WHEN** a delivery record is created with an address
- **THEN** the create returns immediately with no location, and the location appears afterwards
  without any further action

#### Scenario: Existing records with no pin are resolved by the same mechanism

- **WHEN** delivery records stored before this capability existed have an address and no
  location
- **THEN** they are resolved like any other, without being enumerated or migrated

#### Scenario: A provider failure loses no work

- **WHEN** the provider is unavailable or times out while resolving a record
- **THEN** the record keeps its address and no location, and is attempted again later

#### Scenario: A record with an address but no resolvable location is not retried forever in one pass

- **WHEN** a record's address resolves to nothing
- **THEN** the pass completes without stalling on it and moves to the remaining records

#### Scenario: A placed pin is left alone

- **WHEN** a delivery already carries a location, whether derived or placed by hand
- **THEN** the background resolution does not change it

### Requirement: Bounded, sequential, rate-respecting resolution

Background resolution SHALL process records **one at a time**, pausing between provider calls,
so the providers' published rate limits (approximately one request per second) are respected by
construction rather than by configuration.

Each pass SHALL process a bounded number of records and finish, rather than run indefinitely,
so that passes cannot pile up and so the work is observable.

The mechanism SHALL NOT be able to multiply with the web tier: running the API with multiple
worker processes SHALL NOT produce multiple concurrent resolvers, since that would breach the
rate limit invisibly.

#### Scenario: Records are resolved sequentially

- **WHEN** several records await a pin
- **THEN** they are resolved one after another with a pause between provider calls, never
  concurrently

#### Scenario: A pass is bounded

- **WHEN** more records await a pin than a pass will take
- **THEN** the pass resolves up to its bound and finishes, leaving the rest for the next pass

#### Scenario: Scaling the API does not scale the resolver

- **WHEN** the API runs with several worker processes
- **THEN** the number of concurrent background resolvers does not change

### Requirement: Resolution is scoped per record, across tenants

Background resolution runs with no request and therefore no resolved tenant, so it SHALL derive
every scope from the record it is resolving: the tenant and branch it belongs to, and that
branch's business location as the geocoding bias.

It SHALL only read records, resolve locations, and write those locations back. It SHALL NOT
return records to any caller, which is what makes operating across tenants safe here.

#### Scenario: Each record is biased to its own branch

- **WHEN** records of different branches await a pin
- **THEN** each is resolved biased to its own branch's business location, not a shared one

#### Scenario: Records of every tenant are resolved

- **WHEN** records of more than one tenant await a pin
- **THEN** all of them are resolved, without a tenant being selected by a caller

#### Scenario: A branch with no business location still resolves

- **WHEN** a record's branch has no business location set
- **THEN** resolution proceeds without a bias rather than failing or being skipped
