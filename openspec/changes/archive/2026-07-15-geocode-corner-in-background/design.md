## Context

The geocoder resolves a street and returns whatever segment of it the provider picks. Measured
in Riohacha, against intersections resolved from OSM geometry:

| | |
|---|---|
| pin produced today for `Calle 41A #12C-48` | 11.5237002, -72.9067338 |
| `Calle 41 ∩ Carrera 10` | 11.5237489, -72.9064891 — **27 m** from our pin |
| `Calle 41 ∩ Carrera 12C` (the address) | 11.5228503, -72.9117535 — **555 m** from our pin |

The operator's report — *"me lo manda es para la carrera 10 más o menos, no la 12C"* — was
accurate to 27 metres. The same effect measured 3995 m on `Carrera 7 #12-30`, because Carrera 7
crosses Calle 12 at its north end and the provider answered with a segment at its south end.

What the current geocoder throws away is the fix. `parse_street` extracts the cross street
(`12C` → `Carrera 12C`) and drops it, because it was evaluated as a **fallback** and correctly
rejected there: Carrera 12C's own point is 1.48 km from Calle 41. As the **other half of an
intersection** it is exactly the missing datum.

Probes that shape everything below:

- **Nominatim cannot resolve intersections.** `Calle 41 & Carrera 12C` → Carrera 12C's own
  point. `Calle 41 con Carrera 12C` → miss. Intersecting the two matches' `boundingbox` fails:
  each box covers one *way*, not the street, and for this address the boxes do not even overlap.
- **Overpass can**: the node shared by two named ways. `Calle 41 ∩ Carrera 12C` → the corner.
- **Overpass is not fast and not reliable.** Area-scoped queries took 1.6–9.1 s; **1 of 3
  probe requests returned 504**. A bbox-scoped variant (no boundary-name dependency) 504'd
  outright — it is the more expensive query for the server to plan.
- **The tenant filter is skipped without request context** (`filtering.py`: `if tenant_id is
  None: return`), which is what a cross-tenant sweeper needs — and a footgun worth naming.

## Goals / Non-Goals

**Goals:**

- The pin lands on the address's corner when OSM holds both streets.
- Taking an order never waits on a geocoder.
- Work is never lost: a failed or slow lookup is retried, not dropped.
- The providers' 1 req/s policy is respected by construction, not by discipline.
- The deliveries already stored pin-less get resolved by the same mechanism.

**Non-Goals:**

- House-level accuracy. `-48` is metres past the corner; OSM has no addressed buildings here.
- Self-hosting Overpass/Nominatim (the eventual right answer; see Risks).
- Re-resolving pins already set, including hand-placed ones.
- A UI for "geocoding pending" — a null pin already reads as "sin ubicación".

## Decisions

### 1. Overpass for the corner, area-scoped

```
area["name"="Riohacha"]["boundary"="administrative"]->.a;
way(area.a)["name"="Calle 41"]->.w1;
way(area.a)["name"="Carrera 12C"]->.w2;
node(w.w1)(w.w2); out;
```

Area-scoped, not bbox-scoped. A bbox around the branch pin is more robust in principle — it
does not depend on a boundary being *named* — but it 504'd every time in probing, while the
area query answered. Measured behaviour wins over principle here.

The city name comes from reverse-geocoding the branch's business pin once, cached: the branch
settings hold coordinates, not a city.

**Multiple shared nodes** (a divided road: `Calle 15 ∩ Carrera 10` returned two, 18 m apart)
→ take the first by node id. Deterministic, and 18 m is far below this feature's precision.

### 2. The chain: corner, then base-street corner, then street

```
Overpass   Calle 41A ∩ Carrera 12C   -> miss (41A is not in OSM)
Overpass   Calle 41  ∩ Carrera 12C   -> HIT, the corner              <- the real address
Nominatim  Calle 41A / Calle 41      -> the street-level pin (today's behaviour)
otherwise  no pin, placed by hand
```

The letter-suffix fallback that already exists carries into the corner query. The Nominatim
step is kept, not replaced: a street missing from OSM, or an address naming only one street,
still yields today's pin — worse, but not wrong, and strictly better than nothing.

### 3. The database is the queue

"Needs a pin" is a predicate, not a message:

```sql
WHERE latitude IS NULL AND btrim(address_text) <> ''
```

No broker, no new dependency, no delivery guarantees to reason about. Idempotent (a resolved
pin leaves the set), restart-safe (state is the row), self-retrying (a failure simply stays in
the set), and it picks up the 7 existing pin-less deliveries without being told about them.

Alternative — `arq` + Redis: rejected. It adds a dependency and a worker process to gain
immediacy nobody needs, it cannot see the existing backlog, and **concurrent workers would
breach 1 req/s** — the queue's main feature is the one thing this must not have.

### 4. A bounded batch script, not an in-app loop

The sweeper is `python -m scripts.geocode_pending`: take up to N pin-less deliveries, resolve,
exit. Run periodically.

Not an asyncio task on FastAPI startup: uvicorn with `--workers 4` would run **four sweepers**,
quadrupling the request rate against a service that allows one per second. The failure would be
a silent ban, not an error. A script cannot accidentally multiply with the web tier.

Bounded batch + short runtime keeps periodic runs from overlapping; if they ever do, the work is
idempotent — the cost is wasted requests, not corruption.

### 5. Rate limiting is sequential, not configured

One delivery at a time, with a sleep between provider calls. Two providers, ~1 req/s each: the
loop *is* the rate limiter. Nothing to tune, nothing to breach, and the existing per-address
cache means a repeated address costs nothing.

### 6. The sweeper runs without tenant context, deliberately

No request means no `get_current_tenant_id()`, so the automatic filter is skipped and the query
sees every tenant's rows. That is what a sweeper must do — and it is exactly the shape of an
accidental data leak, so it is stated here rather than discovered later.

It is safe because the sweeper answers no one: it reads rows, resolves pins, writes them back,
and never returns data to a caller. Each delivery carries its own `tenant_id` **and
`branch_id`**, so the bias comes from that delivery's own branch settings — a lookup only
possible because deliveries became branch-scoped.

### 7. Geocoding leaves create/update

`create_delivery` and `update_delivery_address` stop awaiting the geocoder; they store the
address and return. `update_delivery_address` additionally **clears the pin** when the address
changes and no explicit pin is given, which puts the row back in the sweeper's set — preserving
the existing "editing an address re-geocodes" behaviour, asynchronously.

An explicit pin still always wins and is never swept.

## Risks / Trade-offs

- **Public Overpass failed 1 request in 3 while probing.** → The sweeper retries by doing
  nothing: the row stays in the set. A delivery may be pin-less for minutes. Acceptable only
  because nothing waits on it — which is the whole point of moving off the request path.

- **This makes public Overpass load-bearing.** It is a free shared service with no SLA. →
  Self-hosting the Colombia extract is the real answer if delivery matters; the sweeper's
  tolerance buys time to decide, it does not remove the need.

- **The pin appears seconds to minutes after the order.** → Nothing renders it as an error; the
  map and the board already handle a null pin. But a dispatcher who looks *immediately* sees no
  dot, where today they see a (wrong) one. Losing a wrong dot is a gain.

- **Street names must match OSM's spelling exactly.** `Calle 41` matches; a tenant writing
  `Cl 41` in an address is normalised by the parser, but OSM's own naming (`Calle 41` vs
  `CALLE 41`) is not something we control. → Overpass name matching is exact; a mismatch is a
  miss and falls back to Nominatim, which fuzzy-matches. The two failure modes complement.

- **A sweeper with no tenant context bypasses the isolation the whole app leans on.** → Named
  in Decision 6. Any future code sharing this entry point inherits the exposure.

- **The corner is not the house.** `-48` metres along the block is unmodelled. → The operator
  has explicitly said the corner is enough.

## Migration Plan

Backend-only; no schema, no data migration.

1. Ship the parser change, the Overpass lookup and the chain.
2. Ship the sweeper script.
3. Take geocoding out of create/update **last** — until the sweeper runs, that would leave new
   deliveries pin-less indefinitely.
4. Schedule the sweeper. First run resolves the existing backlog (the 7 pin-less rows) at
   roughly one delivery per few seconds.

**Rollback:** restore the awaited geocode in create/update and stop the sweeper. Pins already
written stay valid.

## Open Questions

- **How is the sweeper scheduled?** cron, a systemd timer, a container restart policy — this
  repo has no precedent for a recurring job, and the answer depends on how the backend is
  deployed, which is not visible from here.
- **Should a delivery record that geocoding has given up on be marked**, so the board can say
  "sin ubicación — ponla a mano" instead of a silent blank, and so the sweeper stops retrying
  it forever? Today a null pin is ambiguous between "not tried yet", "provider was down" and
  "hopeless". It is a schema change; it belongs with the dispatch board work.
- **Does the city name for the Overpass area hold for every branch?** Reverse-geocoding the
  business pin is an assumption, not a guarantee, for a branch on a municipal boundary.
