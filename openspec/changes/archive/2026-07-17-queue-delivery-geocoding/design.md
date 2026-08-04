## Context

Pins are resolved by `scripts.geocode_pending`, which nothing invokes. The resolver itself is
built and verified — it puts `Calle 41A #12C-48` on its corner, 555 m from where the old pin
landed — but an operator taking an order today sees "sin ubicación" until someone runs a command
by hand. The capability exists and is inert.

The archived change (`2026-07-15-geocode-corner-in-background`) left this as Open Question #1 and
rejected a queue in Decision 3. That rejection had three legs:

| objection | still true? |
|---|---|
| "it cannot see the existing backlog" | **yes** — so the database predicate is kept, not replaced |
| "concurrent workers would breach 1 req/s" | **yes** — so concurrency is forbidden, in the spec |
| "immediacy nobody needs" | **no** — this is the leg being overturned |

Constraints that do not move:

- **Nominatim and Overpass allow ~1 req/s and punish a breach with a silent ban**, not an error.
  Nothing here may be able to run two resolutions at once.
- **Overpass is slow (1.6–9.1 s) and sheds ~1 request in 3** (504). Verified again while building
  this: the operator's address took four attempts.
- **The codebase is async end to end** — SQLAlchemy async, asyncpg, httpx.
- **The cache must survive process restarts.** A resolver is a short-lived process; with
  `CACHE_BACKEND=memory` every run re-spends provider requests. Measured: 2 requests per pass
  forever vs. 0 after the first with `redis`.

## Goals / Non-Goals

**Goals:**

- A delivery's pin appears within seconds of the order, without anyone running anything.
- No delivery is ever lost, whatever fails — Redis, a job, the worker, a provider.
- One request per second remains true by construction, not by configuration.
- The existing backlog keeps resolving through the same mechanism.

**Non-Goals:**

- Immediacy at the cost of the guarantee. If the two conflict, the guarantee wins.
- Distributing the work. The rate limit means the ceiling is one resolution at a time — there is
  nothing to scale out, ever.
- Re-resolving pins already set, including hand-placed ones. Unchanged.
- Replacing `scripts.geocode_pending`. It stays as the manual drain and the rollback path.
- Marking a delivery as hopeless so the sweep stops retrying it. Still open, still deferred.

## Decisions

### 1. arq, not Celery

The user asked for Celery. arq is chosen instead, and the difference is not taste:

- **arq is asyncio-native.** The resolver is `async` all the way down; an arq job *is* a coroutine.
- **Celery is synchronous at its core.** Every task would wrap `asyncio.run(...)` around an async
  call graph, creating and tearing down an event loop per job, and would need its own sync DB
  session story next to the async one the app already has.
- **arq's dependency is Redis**, which is already running and already configured (`REDIS_URL`).
  Celery would add a broker abstraction over the same Redis for no gain here.
- Celery's real strengths — routing, chords, huge fan-out, multi-language workers — are things a
  1 req/s pipeline can never use.

Alternative considered: **a plain OS cron calling the existing script.** Simpler than everything
below, zero dependencies, and genuinely close in outcome — Overpass's own latency means a queue
saves ~60 s at best. Rejected because the operator's complaint is precisely about the delay to
first pin, and a queue plus the cron sweep is strictly better than the cron sweep alone.

### 2. The queue announces; the database decides

```
create delivery ──> enqueue job ──> resolve now              (latency)
                                     ↑
    cron sweep every minute ─────────┘                        (guarantee)
    WHERE latitude IS NULL AND btrim(address_text) <> ''
```

The enqueue is a **hint**, never the record of what needs doing. The set of work stays the
predicate over the rows. This is the whole reason the archived design's objection does not bite:

- Redis unreachable when the order is taken → no job → the sweep gets it.
- A job dies mid-flight → the row still has no pin → the sweep gets it.
- A delivery created by some future path that forgets to enqueue → the sweep gets it.
- The pin-less rows already in the database → the sweep gets them, as it does today.

Duplicate work is free: a job and the sweep both reaching the same delivery is idempotent, because
the resolver skips any row that already has a location. No job IDs, no locks, no dedup.

### 3. One worker, `max_jobs = 1`

The rate limit is a hard ceiling, so the worker's concurrency is pinned at 1 and exactly one worker
runs. Both the queued job and the cron sweep execute in that one worker, so they are serialised
against each other for free — a job cannot overlap a sweep.

The cron is declared `unique=True` (arq's default) so that even if a second worker were started,
the *sweep* would not double-run. That is a partial guard, not a fix: two workers would still
process two queued jobs at once. Concurrency is therefore stated in the spec as a requirement, and
named in Risks as the sharpest edge in this change.

### 4. A job retries a few times, then lets go

The job resolves; if no pin came back, it raises arq's `Retry(defer=job_try * 5)` up to a small
bound, then gives up and leaves the row to the sweep.

Retrying on "no pin" deliberately does not distinguish a 504 from an address that matches nothing,
because **the cache makes the distinction free**: a transient failure is not cached and is really
retried, while a genuine no-match is cached and the retry costs zero provider requests. This is why
Decision 6 is a prerequisite and not a nicety — without a shared cache, retrying junk addresses
would burn real requests.

Bound and backoff: 4 tries at 5 s, 10 s, 15 s. Against a 1-in-3 shed rate that resolves ~99% of
corners within ~30 s, which is the immediacy this change is for. What escapes falls to the sweep.

### 5. Enqueue never fails an order

The enqueue is wrapped and swallowed: a delivery is created whether or not Redis answers. This
keeps the request path's contract — taking an order waits on nothing and fails for nothing outside
itself — and is only safe to do because of Decision 2. Without the sweep, swallowing here would
silently lose the pin.

It does add one Redis round-trip (~1 ms, local) to create. That is not a provider call and does not
reintroduce what this whole line of work removed.

### 6. Redis is required, for the cache as well as the queue

`CACHE_BACKEND=redis` moves from "prod option" to "required for the geocoder to behave as
specified". A separate, short-lived worker process cannot carry an in-process cache: the city
lookup that the design promised costs "one request per branch, ever" becomes one per run, the
always-failing `Calle 41A ∩ Carrera 12C` probe re-spends the 504 exposure every time, and
unresolvable addresses re-query forever.

### 7. Where the enqueue lives

`DeliveryService` gains an optional `GeocodeQueue` port (domain), implemented by an arq adapter
(infrastructure). The service enqueues from `create_delivery` and from the address-edit path that
clears the pin — the two places that put a row into the predicate's set. The layering rule holds:
application depends on the port, infrastructure implements it.

## Risks / Trade-offs

- **Two workers = a silent ban.** The failure mode is not an exception; it is the providers quietly
  refusing us, and pins stopping for everyone. → `max_jobs = 1` in code, a spec requirement, and
  a deployment that starts exactly one. This is the thing most likely to be broken later by someone
  scaling "the workers" without knowing why one exists.

- **The sweep now lives inside the arq worker, which needs Redis.** Redis down means the queue AND
  the safety net are down — previously an OS cron would have kept sweeping. → `scripts.geocode_pending`
  is deliberately retained and unchanged; if Redis reliability ever matters, scheduling that script
  at OS level restores an out-of-band backstop. Named because it is a real coupling that the
  previous design did not have.

- **A required always-on process the repo has no precedent for.** Nothing here supervises it, and a
  worker that is silently dead looks exactly like Overpass being slow. → The sweep's log line
  (found/resolved/pending) is the health signal; observability of the worker is not solved here.

- **Public Overpass stays load-bearing and has no SLA.** → Unchanged from the archived design:
  self-hosting the Colombia extract is the real answer; retries and the sweep buy time.

- **The pin still appears after the order, just sooner.** A dispatcher looking instantly sees no
  dot for a few seconds. → Nothing renders that as an error, and a briefly missing dot beats the
  confidently wrong one this line of work removed.

## Migration Plan

Backend-only; no schema, no data migration.

1. Add `arq`; add the port, the adapter and the worker module.
2. Wire the enqueue into create and the address edit.
3. Start the worker. Its first cron sweep drains whatever is pending.
4. `CACHE_BACKEND=redis` — already applied to `.env`; required wherever this runs.

**Rollback:** stop the worker and schedule `poetry run python -m scripts.geocode_pending` on a
timer. Nothing else has to change: the script is the same code path the cron job calls, and pins
already written stay valid. That the rollback is "the design we just moved away from" is
intentional — it is why the script survives.

## Open Questions

- **What supervises the worker?** The archived question ("how is the sweeper scheduled?") narrows
  rather than disappears: instead of a timer, it needs one always-on process. The answer still
  depends on how the backend is deployed, which is not visible from here.
- **Should a delivery geocoding has given up on be marked**, so the board can say "sin ubicación —
  ponla a mano" and the sweep stops retrying it forever? Still open, still a schema change, still
  belongs with the dispatch board. `uuu` and `Sin dirección exacta` sit in the set today; with the
  Redis cache they now cost ~0 per pass, which lowers the urgency without answering it.
