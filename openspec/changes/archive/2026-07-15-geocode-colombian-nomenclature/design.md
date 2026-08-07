## Context

`NominatimGeocoder.geocode()` sends the stored `address_text` verbatim as `q=` and trusts the
top hit. That held while addresses were clean streets. It does not hold for the nomenclature a
Colombian restaurant actually receives.

Measured against live Nominatim, biased to Riohacha, through this repo's own adapter:

| query | outcome |
|---|---|
| `calle 41A #12C - 48, Riohacha` | MISS |
| `Calle 41A #12C-48, Riohacha` | MISS |
| `Calle 41A 12C 48, Riohacha` | MISS |
| `Calle 41A, Riohacha` | HIT → `k 13 # 41a - 69, **Calle 44**, San Isidro` |
| `Calle 41, Riohacha` | HIT → `Calle 41, Divino Niño` |
| `Carrera 12C, Riohacha` | HIT → `Carrera 12C, José Arnoldo Marín` |

Three facts fall out, and each one shapes a decision:

1. **The house number is unmatchable.** OSM's Riohacha has street geometry, not addressed
   buildings. Any query carrying `#12C-48` misses.
2. **Nominatim would rather be wrong than empty.** Asked for a street it does not have, it
   fuzzy-matched a *house number* containing "41a" on a different street. Structured search
   (`street=`/`city=`) returns the identical wrong hit, so this is not fixable by syntax.
3. **The distance between candidates is decisive.** `Calle 41` sits **190 m** from the rejected
   41A match; `Carrera 12C` sits **1.48 km** away. With `ring_step_km = 1.5`, one is a rounding
   error and the other is a different ring.

The existing adapter already asks for `addressdetails=1` and reads `address.neighbourhood`, so
`address.road` is in the payload and verification costs no extra request.

## Goals / Non-Goals

**Goals:**

- A real Colombian address yields a street-level pin instead of nothing. **Street-level means
  the street's length**, not a fixed radius — measured 90 m and 3995 m from the true corner in
  two Riohacha addresses (see Risks). Resolving the corner needs an intersection query, which
  is a separate change.
- A confidently wrong pin is rejected rather than stored.
- The full address, house number included, stays untouched in `address_text`.
- Geocoding stays a best-effort side lookup: it never raises into order-taking.

**Non-Goals:**

- Door-level accuracy. Street-level is the ceiling of OSM data here.
- Cross-street fallback (see Decision 3).
- Self-hosted Photon: same OSM data, same missing house numbers.
- Backfilling deliveries already stored pin-less.
- Intersection geometry (Calle 41A × Carrera 12C). Nominatim returns points, not the street
  geometries an intersection needs; that is Overpass territory and far past this problem.

## Decisions

### 1. Parse the nomenclature, query only the street

`Calle 41A #12C-48` → query `Calle 41A`. The `#12C-48` never reaches the geocoder and never
leaves `address_text`.

The parser recognises the type (`calle/cll/cl`, `carrera/cra/kra/krr/kr/k`, `avenida/av`,
`diagonal/diag/dg`, `transversal/transv/tv`), canonicalises it (`cra` → `Carrera`), and takes
the street number with its optional letter (`41A`).

**It must fail soft.** An address it cannot parse falls through to today's behaviour — query as
written — never to an exception. A geocode failure must never break taking an order, which is
why `_geocode_address` already wraps the call in a bare except.

### 2. Verify `address.road` against the street we asked for; a mismatch is a miss

The single most valuable line in this change. Compare case-insensitively; when the returned
road does not name the requested street, treat it as no match.

This is what turns "Nominatim would rather be wrong than empty" into "we would rather be empty
than wrong". A null pin is an honest gap the dispatcher fills from the map. A wrong pin is a
driver in the wrong barrio, a lie on the coverage map, and — once the ring inference lands —
a delivery filed under the wrong ring.

Alternative — trust the top hit and rank by `importance`: rejected. The wrong hit *was* the
top hit, with a plausible importance. Nominatim's confidence does not encode "this is the
street you asked for".

### 3. Fall back to the base street; never to the cross street

`Calle 41A` unverifiable → try `Calle 41`. Measured 190 m — 41A is literally the block beside
41, which is what the suffix means.

The cross street is the tempting one and it is a trap. `Calle 41A #12C-48` names Carrera 12C,
Carrera 12C *is* in OSM, and it verifies cleanly — so a naive chain would take it and look
successful. But Nominatim returns that street's representative point, measured 1.48 km from
Calle 41: the right street by the wrong end, one full ring band away, indistinguishable in the
data from a good pin. **A verified-but-far match is more dangerous than an unverified one**,
because nothing downstream can tell. Excluded on the measurement, not on taste.

Chain, two attempts maximum:

```
street ("Calle 41A")  -> verify -> hit? done
base   ("Calle 41")   -> verify -> hit? done          (only when a letter suffix was present)
otherwise             -> no pin, placed by hand
```

### 4. Cache the resolved address, not each candidate

The cache key stays the caller's address + bias, so a repeated `calle 41A #12C - 48` costs zero
requests — including a repeated *failure*, via the existing `_MISS` sentinel. The candidate
chain runs only on a genuine cache miss.

This matters against public Nominatim's 1 req/s policy: two candidates is two requests, so the
chain is capped at two and the cross street's absence is a throughput win as well as a
correctness one.

Transient failures keep bypassing the cache, as fixed earlier: a 403 or timeout must not pin an
address to null for the TTL.

## Risks / Trade-offs

- **Fewer pins than before.** Rejecting wrong matches means some addresses that used to get a
  (bad) pin now get none. → That is the point. Rings are 1.5 km; a wrong pin lands in the wrong
  one, and the dispatcher has no way to know. The manual picker in `/dispatch` is the escape.

- **The parser meets free text typed under pressure.** `cll 41 a # 12 c 48`, `41A #12C-48` with
  no type at all, a barrio name instead of a street. → Fail soft: unparseable falls through to
  the address as written, which is exactly today's behaviour. The change can only add pins over
  the current baseline for parseable input, never remove the existing path — except where it
  deliberately rejects a wrong hit.

- **Two requests per new address on the fallback path**, against a 1 req/s public policy. →
  Capped at two, cached per address, and misses are cached too. A busy service should move to a
  self-hosted Nominatim — which does fix throughput, unlike Photon, which fixes nothing here.

- **`address.road` is not always present** (a match on a suburb or a POI has no road). → Absent
  road = unverifiable = miss. Strict by design.

- **The 190 m / 1.48 km numbers are two samples in one city.** They justify the ordering, they
  do not prove it universally. → The ordering is also justified from first principles: 41A is
  defined as adjacent to 41, whereas a cross street's centroid has no defined relationship to
  the address at all.

## Migration Plan

Backend-only, no schema, no data migration. Deploy the adapter; new and re-edited addresses
geocode through the new path. Existing pins are untouched.

**Rollback:** revert the adapter. Pins written under the new logic stay valid — they are just
pins.

## Open Questions

- Should an address that fails every candidate be *marked* as "geocoding tried and failed", so
  the board can show "sin ubicación — ponla a mano" rather than a silent blank? Today a null
  pin is ambiguous between "not geocoded yet" and "geocoded and hopeless". Leaning yes, but it
  is a schema change and belongs with the dispatch board work, not here.
- The 4 deliveries already stored with `address_text = ''` and the 7 with no pin will never
  resolve on their own. A one-off re-geocode pass over the pin-less ones with a real address
  would be cheap once this lands — but it is a separate decision.
