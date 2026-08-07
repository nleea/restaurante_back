## 1. The dependency and the settings

- [x] 1.1 Add `arq` to `pyproject.toml` and lock it; it reuses the existing `REDIS_URL`
- [x] 1.2 Settings for the worker: how many records a periodic pass takes, and how often it runs — no setting for concurrency, which is not tunable (design §3)
- [x] 1.3 `CACHE_BACKEND=redis` is already applied to `.env`; make the geocoder's need for a durable cache explicit where it is configured, so nobody "optimises" it back to memory

## 2. The port and its adapter

- [x] 2.1 `GeocodeQueue` port on the delivery domain: announce that one delivery needs a pin. Nothing more — it is a hint, not a work record (design §2)
- [x] 2.2 Arq adapter implementing it, over `REDIS_URL`
- [x] 2.3 The adapter swallows its own failures: an announcement that cannot be sent is logged and dropped, never raised (design §5)
- [x] 2.4 Injectable, so tests never touch Redis

## 3. Announcing from the request path

- [x] 3.1 `DeliveryService` takes an optional `GeocodeQueue`; with none it behaves exactly as today
- [x] 3.2 `create_delivery` announces when it stored an address and no pin — and only then: an explicit pin is never swept, so announcing it would be a lie
- [x] 3.3 `update_delivery_address` announces when it clears the pin — the same two cases that put a row into the predicate's set
- [x] 3.4 Wire the adapter into the API deps. This is the one place a Redis round-trip enters the request path; it must stay off the provider path entirely

## 4. The worker

- [x] 4.1 `delivery/infrastructure/worker.py` with `WorkerSettings`: the job, the cron sweep, and `max_jobs = 1`
- [x] 4.2 The job resolves ONE delivery, by tenant and id, reusing the existing resolver — no second implementation of resolution
- [x] 4.3 The job re-reads the record and does nothing if it already has a location: this is what makes a duplicate announcement free (design §2)
- [x] 4.4 No pin came back → `Retry(defer=job_try * 5)`, bounded at 4 tries, then give up and leave it to the sweep (design §4)
- [x] 4.5 The cron sweep runs `PendingGeocoder` on the same bound as the script, `unique=True`, every minute
- [x] 4.6 One session and one geocoder per job/pass, opened and closed cleanly — the worker is long-lived and must not leak connections
- [x] 4.7 Log what the worker did, so a dead worker does not look like a slow Overpass (design → Risks)

## 5. What must not break

- [x] 5.1 `scripts.geocode_pending` keeps working, unchanged: it is the manual drain AND the rollback path (design → Migration)
- [x] 5.2 The predicate stays the authority — nothing anywhere may make a pin depend on a job having been enqueued

## 6. Tests (fakes, no Redis, no network)

- [x] 6.1 `create_delivery` announces exactly once when it stores an address with no pin
- [x] 6.2 `create_delivery` does NOT announce when given an explicit pin
- [x] 6.3 `update_delivery_address` announces when it clears the pin; does not when an explicit pin survives; does not when the address is untouched
- [x] 6.4 A queue that raises does not fail the create — the delivery is still returned (spec: "An announcement that cannot be sent does not fail the order")
- [x] 6.5 `DeliveryService` with no queue behaves exactly as it does today
- [x] 6.6 The job resolves a pending delivery and writes the pin
- [x] 6.7 The job leaves an already-located delivery untouched and issues no provider call (spec: "Resolving the same record twice changes nothing")
- [x] 6.8 The job retries on no pin, is bounded, and stops retrying rather than looping forever
- [x] 6.9 `WorkerSettings.max_jobs == 1` is asserted — the rate limit is a requirement, so it gets a test, not a comment (spec: "a burst of announcements does not become a burst of requests")
- [x] 6.10 `poetry run pytest`, `poetry run ruff check .` and `poetry run mypy src` green

## 7. Prove it end to end

- [x] 7.1 Start the worker; create a delivery through the API with the real address; confirm the caller is not blocked and the pin appears within seconds without running anything
      → create 201 in **82 ms**, no pin; announced job fired 0.3 s later; pin at **~12 s**: `11.5228503, -72.9117535` (the corner). Nothing was run by hand.
- [x] 7.2 Confirm the first cron sweep drains whatever was already pending, without being told about it
      → worker started 18:22:44; cron fired by itself at 18:23:00 and resolved `1/3` pre-existing pin-less rows. The 2 left are junk (`uuu`, `Sin dirección exacta`).
- [x] 7.3 Stop Redis (or point it at a dead address), create a delivery: the create still succeeds. Restore Redis: the sweep resolves it. This is the guarantee the whole design rests on (design §2)
      → against a dead Redis the create returned **80 ms** (was 5119 ms — see the fail-fast fix below) and the sweep resolved it at the next tick (~58 s). A lost announcement costs latency, never the pin.
- [x] 7.4 Confirm an already-pinned delivery is never touched by either path
      → re-announced a pinned record: job returned `not_needed`, **0 provider requests**, pin unchanged.
- [x] 7.5 Confirm the second cache run costs zero provider requests, i.e. `CACHE_BACKEND=redis` is really in effect (spec: "A repeated address costs no provider request")
      → same address, second delivery: pin in **~1 s** (vs 12 s) at **0 provider requests**.
- [x] 7.6 Keep these as scratchpad probes, NOT tests — the suite must not need Redis, a worker, or the network
      → probes live in the session scratchpad. The suite needed a fix to honour this: `.env`'s `CACHE_BACKEND=redis` was reaching the tests and opening real Redis connections (121 errors). `tests/conftest.py` now pins `CACHE_BACKEND=memory`, as it already did for `DATABASE_URL`.

## 8. Hand over what has to be run

- [x] 8.1 Document the worker command and that a deployment runs EXACTLY ONE, with why — a reader who does not know about the 1 req/s ban will scale it
      → `backend/README.md` (new section, with the "EXACTAMENTE UNO. No escalar." callout and the silent-ban reason) and `backend/CLAUDE.md` commands block.
- [x] 8.2 Record the rollback: stop the worker, schedule `scripts.geocode_pending` on a timer
      → same README section; the script is named as both the manual drain and the rollback path.
- [x] 8.3 Leave the supervision question stated where it will be found, not buried — nothing here keeps the worker alive (design → Open Questions)
      → stated in the README section as an open item ("Sin resolver: qué supervisa al worker"), next to the command it concerns, with the sweep log line named as the only health signal.
