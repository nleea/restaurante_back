# delivery-geocoding-worker

## Purpose

Resolve delivery pins outside the request path. Delivery records store an address and, until
resolved, no location; this capability derives the pin from the address in the background —
sequentially, within the providers' rate limits, scoped per record across tenants — so that
taking an order never waits on a geocoding provider.

The geocoding itself (parsing, intersection resolution, verification, fallbacks) belongs to the
`delivery-management` capability's geocoder; this capability owns only *when and how* that
geocoder is driven.

## Requirements

### Requirement: Resolve delivery pins outside the request path

The system SHALL resolve delivery pins in the background, so that taking an order never waits
on a geocoding provider. Providers answer in seconds and fail intermittently — measured at
1.6–9.1 s with one request in three returning 504 — which is tolerable only where nobody is
waiting.

The set of work SHALL be derived from the delivery records themselves — a record that has an
address and no location needs a pin. State lives in the row, so the work is idempotent, survives
a restart, and retries by simply remaining unresolved. This derived set SHALL remain
authoritative: it, and not any queue, defines what needs a pin.

Records needing a pin MAY additionally be **announced** to the resolver when they are created or
when an address edit clears their pin, so a pin appears in seconds rather than waiting for the
next periodic pass. An announcement SHALL be treated as a latency optimisation only. It SHALL
NOT be required for a record to be resolved, SHALL NOT be relied upon as a record of work, and
SHALL NOT be able to fail the operation that produced it — a record whose announcement is lost,
never sent, or never delivered SHALL still be resolved by the periodic pass.

Resolution SHALL be periodic and unattended: the system SHALL resolve pending records without a
person invoking anything.

Records already carrying a location SHALL NOT be re-resolved, including hand-placed pins. A
record announced more than once, or announced and also found by a periodic pass, SHALL resolve
to the same outcome as if it had been processed once.

#### Scenario: A new delivery gets its pin without blocking the order

- **WHEN** a delivery record is created with an address
- **THEN** the create returns immediately with no location, and the location appears afterwards
  without any further action

#### Scenario: A new delivery is resolved within seconds, not at the next pass

- **WHEN** a delivery record is created with an address and the resolver is running
- **THEN** its resolution begins without waiting for the next periodic pass

#### Scenario: Nothing is invoked by hand

- **WHEN** deliveries await a pin and no person runs any command
- **THEN** they are resolved anyway

#### Scenario: A lost announcement still resolves

- **WHEN** a record needing a pin is never announced, or its announcement is lost
- **THEN** the periodic pass finds it by its address and missing location, and resolves it

#### Scenario: An announcement that cannot be sent does not fail the order

- **WHEN** the delivery record is created but the announcement cannot be delivered
- **THEN** the delivery is still created successfully, and the record is resolved by the periodic
  pass

#### Scenario: Existing records with no pin are resolved by the same mechanism

- **WHEN** delivery records stored before this capability existed have an address and no
  location
- **THEN** they are resolved like any other, without being enumerated or migrated

#### Scenario: A provider failure loses no work

- **WHEN** the provider is unavailable or times out while resolving a record
- **THEN** the record keeps its address and no location, and is attempted again later

#### Scenario: A transient provider failure is retried promptly, then left to the periodic pass

- **WHEN** resolving an announced record yields no location
- **THEN** it is retried a bounded number of times with increasing delay, and if it still yields
  no location it is left for the periodic pass rather than retried indefinitely

#### Scenario: Resolving the same record twice changes nothing

- **WHEN** a record is announced more than once, or is announced and also found by a pass
- **THEN** the outcome is the same as a single resolution, and no location is overwritten

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

Each periodic pass SHALL process a bounded number of records and finish, rather than run
indefinitely, so that passes cannot pile up and so the work is observable.

The mechanism SHALL NOT be able to multiply with the web tier: running the API with multiple
worker processes SHALL NOT produce multiple concurrent resolvers, since that would breach the
rate limit invisibly.

Announcing records SHALL NOT introduce concurrency: however many records are announced at once,
the resolver SHALL process at most one at a time, and an announced resolution SHALL NOT run
concurrently with a periodic pass. The providers' rate limit is a ceiling on the whole system, so
the resolver SHALL NOT be horizontally scalable — a deployment SHALL run exactly one.

#### Scenario: Records are resolved sequentially

- **WHEN** several records await a pin
- **THEN** they are resolved one after another with a pause between provider calls, never
  concurrently

#### Scenario: A burst of announcements does not become a burst of requests

- **WHEN** several delivery records are created at once and all are announced
- **THEN** they are resolved one at a time, and the provider request rate is unchanged from
  resolving them by a periodic pass

#### Scenario: An announced resolution does not overlap a periodic pass

- **WHEN** a record is announced while a periodic pass is running
- **THEN** the two do not issue provider requests concurrently

#### Scenario: A pass is bounded

- **WHEN** more records await a pin than a pass will take
- **THEN** the pass resolves up to its bound and finishes, leaving the rest for the next pass

#### Scenario: Scaling the API does not scale the resolver

- **WHEN** the API runs with several worker processes
- **THEN** the number of concurrent background resolvers does not change

### Requirement: Resolution state is shared across resolver runs

Cached provider results SHALL be durable across resolver runs, and SHALL NOT be held in process
memory alone. The resolver is a process separate from the API and is restarted over its lifetime,
so state that makes resolution cheap has to outlive any single run to be worth anything.

Without this, every run re-spends provider requests it has already paid for: a branch's city
would be resolved once per run instead of once per branch, an address known to resolve to nothing
would be re-queried on every pass, and a candidate query known to fail would re-spend its share of
the providers' failure rate each time. Measured: a per-process cache re-spent 2 provider requests
on every pass, where a shared cache spent 0 after the first.

#### Scenario: A repeated address costs no provider request

- **WHEN** an address is resolved, the resolver restarts, and the same address is resolved again
- **THEN** the second resolution issues no provider request

#### Scenario: An unresolvable address stops costing requests

- **WHEN** an address that matches nothing has been attempted, and later passes encounter it again
- **THEN** those passes issue no provider requests for it

#### Scenario: A branch's city is resolved once, not once per run

- **WHEN** records of the same branch are resolved across several resolver runs
- **THEN** the branch's city is not re-resolved from the provider on each run

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
