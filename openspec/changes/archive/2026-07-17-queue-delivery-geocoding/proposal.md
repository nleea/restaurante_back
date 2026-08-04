## Why

Geocoding left the request path, and nothing took over running it. The pin resolver is a script
(`scripts.geocode_pending`) that no cron, timer or process invokes — so it only runs when someone
types the command. This is not theoretical: an operator created a delivery for
`Calle 41A # 12C-48`, saw **"sin ubicación"**, and the record stayed pin-less until the script was
run by hand. Every delivery taken today has the same fate.

The archived change named this as its first Open Question — *"How is the sweeper scheduled? cron, a
systemd timer, a container restart policy — this repo has no precedent for a recurring job"* — and
deferred it. This answers it.

It also revisits that change's Decision 3, which rejected a queue on the grounds that it *"adds a
dependency and a worker process to gain immediacy nobody needs, it cannot see the existing backlog,
and concurrent workers would breach 1 req/s"*. Two of those three objections stand and are honoured
below rather than argued away: the backlog is still resolved by the database predicate, and
concurrency is still forbidden. The third — that nobody needs immediacy — is the one being
overturned: a dispatcher who takes an order and looks at the board expects a dot, and a pin that
waits for the next cron tick is a worse answer than one that arrives while they are still looking.

## What Changes

- **A worker process** (`arq`) resolves delivery pins. Async-native, so it runs the existing async
  resolver directly. Celery was considered and rejected: it is synchronous at its core, and every
  task would need its own `asyncio.run` over a codebase that is async end to end (SQLAlchemy async,
  asyncpg, httpx).
- **A resolution job is enqueued** when a delivery is created with an address and no pin, and when
  an address edit clears the pin. This is what buys immediacy: the pin lands in seconds instead of
  waiting for a tick.
- **The periodic sweep is kept**, as a cron job inside the same worker, reading the same predicate
  (`latitude IS NULL AND btrim(address_text) <> ''`). The queue is an accelerator, never the record
  of what needs doing. This is what preserves the archived design's strongest property: a lost job,
  an unavailable Redis, or a delivery created by a path that forgets to enqueue all still resolve.
- **Single-concurrency becomes a stated requirement**, not a configuration note. Nominatim and
  Overpass allow roughly one request per second and punish a breach with a silent ban, not an error.
- **A job retries a bounded number of times** before deferring to the sweep. Measured need: the
  address above took four attempts, because public Overpass returned 504 on one request in three.
- **Enqueueing never fails an order.** If Redis is unreachable, the delivery is still created and
  the sweep resolves it.
- **Redis becomes required for the geocoder to behave as designed.** The worker is a separate
  process, so an in-process cache is discarded on every run: measured, a `memory` backend re-spends
  2 provider requests every pass where `redis` spends 0 after the first.

## Capabilities

### New Capabilities

None. The capability already exists; this changes how it is driven.

### Modified Capabilities

- `delivery-geocoding-worker`: the work set is currently specified as derived from the records
  **"rather than from a message queue"**. That becomes: derived from the records **and**
  additionally announced through a queue for latency, with the records remaining authoritative.
  Adds requirements for bounded job retry, for enqueue never failing the originating operation,
  and for a durable cache across resolver runs. The existing sequential/bounded/rate-respecting and
  per-record-scoping requirements are unchanged and now constrain the worker's concurrency.

## Impact

- **Dependency**: `arq` (async task queue on Redis). Redis is already running and `REDIS_URL` is
  already configured.
- **New process**: one worker (`arq restaurante.modules.delivery.infrastructure.worker.WorkerSettings`),
  which must run for pins to appear. Deployment must start it alongside the API.
- **Operational constraint**: exactly one worker with `max_jobs = 1`. Scaling it out is a silent
  ban, not an error — this is the sharpest edge in the change.
- **Code**: a queue port on the delivery domain; an `arq` adapter; a worker module; `DeliveryService`
  gains an optional queue collaborator and enqueues from `create_delivery` /
  `update_delivery_address`.
- **Config**: `CACHE_BACKEND=redis` (already applied to `.env`); `arq` reuses `REDIS_URL`.
- **Retained**: `scripts.geocode_pending` stays runnable by hand — it is the same code path the
  cron job calls, and the way to drain a backlog on demand.
- **Not addressed**: whether a delivery that geocoding has given up on should be marked so the
  sweep stops retrying it. Still open, still belongs with the dispatch board.
