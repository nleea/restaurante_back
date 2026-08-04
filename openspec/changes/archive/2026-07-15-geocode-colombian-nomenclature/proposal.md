# Geocode Colombian nomenclature: parse the street, verify the match, never guess

## Why

The geocoder was built assuming a clean street would arrive ("Calle 20", "Carrera 15"). Real
orders do not arrive that way. A real address typed today — **`calle 41A #12C - 48, Riohacha`**
— produced **no pin at all**.

Probing live Nominatim from this repo's adapter shows why, and the second finding is worse than
the first:

```
'calle 41A #12C - 48, Riohacha'   MISS
'Calle 41A #12C-48, Riohacha'     MISS
'Calle 41A 12C 48, Riohacha'      MISS      <- any variant carrying the house number
'Calle 41A, Riohacha'             HIT ... to "k 13 # 41a - 69, Calle 44, San Isidro"
```

1. **OSM has Riohacha's streets, not its house numbers.** The `#12C-48` is noise to the
   geocoder — and gold to the driver. Every variant carrying it misses.

2. **"Calle 41A" is not in OSM, so Nominatim answers with a confident wrong pin**: a house
   whose *number* contains "41a", sitting on **Calle 44**. Structured search (`street=`/`city=`)
   returns the same wrong hit — this is not a syntax problem.

A confidently wrong pin is worse than none: it sends a driver to the wrong place, it lies on
the coverage map, and it will poison the ring inference later. Nothing today detects it.

The failure is silent and total for the addresses this restaurant actually receives, which is
why it only surfaced the first time a real one was typed.

## What Changes

- **Parse Colombian nomenclature** before geocoding. `Calle 41A #12C-48` → the street is
  `Calle 41A`; the `#12C-48` is dropped **from the query only** and stays verbatim in
  `address_text`, where the driver needs it. Handles the common type spellings
  (`calle/cll/cl`, `carrera/cra/kra/kr/k`, `avenida/av`, `diagonal`, `transversal`).

- **Verify every match.** `addressdetails` already returns `address.road`; when it does not
  name the street we asked for, the result is **rejected as a miss**. Measured:

  ```
  asked 'Calle 41A'    road 'Calle 44'      REJECT   <- the confident wrong pin
  asked 'Calle 41'     road 'Calle 41'      accept
  asked 'Carrera 12C'  road 'Carrera 12C'   accept
  asked 'Calle 15'     road 'Calle 15'      accept
  ```

- **Fall back to the base street** when a letter-suffixed street does not exist: `Calle 41A` →
  `Calle 41`. Measured at **190 m** from the rejected 41A match — 41A and 41 really are
  neighbours.

- **BREAKING (behaviour):** an address that previously produced a wrong pin now produces
  **none**, and is placed by hand. Fewer pins, but no lies.

Explicitly **out of scope**, and each for a reason worth recording:

- **No cross-street fallback.** `Calle 41A #12C-48` also names Carrera 12C, which *does* exist
  in OSM — but Nominatim returns that street's centroid, measured **1.48 km** from Calle 41.
  With `ring_step_km = 1.5`, that is a whole ring band wrong. The right street by the wrong end
  is not an approximation, it is a different place.
- **No self-hosted Photon.** It reads the same OSM data: if the house number is not there, no
  OSM-based engine invents it. The gap is the data, not the engine.
- **No door-level accuracy, and no corner either.** This resolves the *street*, and the
  provider answers with an arbitrary segment of it, so the error is the street's length —
  measured 90 m and **3995 m** from the true corner on two Riohacha addresses. The `#12C-48`
  names the cross street and would pin the corner, but that needs an intersection query
  (Overpass), which is a separate change. Exactness beyond that needs the customer's shared
  location — that parser already exists in `/dispatch`.
- **No backfill** of the deliveries already stored without a pin.

## Capabilities

### New Capabilities

None. This makes the existing geocoder survive contact with real Colombian addresses.

### Modified Capabilities

- `delivery-management`: **Geocode a delivery address to an approximate pin** — the geocoder
  parses the nomenclature, verifies the returned road against the requested street, falls back
  to the base street, and treats an unverifiable match as no match.

## Impact

**Backend only.** The frontend paints whatever pin it is given; nothing there changes.

- `delivery/infrastructure/geocoder.py` — address normalisation, the candidate chain, and the
  road verification. Today `_query` takes the top hit on trust.
- The adapter already requests `addressdetails=1`, so verification needs no extra call.
- Each rejected candidate costs another request. Public Nominatim's policy is 1 req/s and the
  cache is per resolved address — the candidate chain must stay short (2 attempts) and the
  existing `_MISS` sentinel keeps a repeat address off the wire.
- `tests/modules/delivery/test_geocoder_adapter.py` — mocked-transport cases for the parser,
  the rejection and the fallback. The live probes that produced the numbers above are
  evidence, not tests: they must not become network-dependent tests.

**Risk**

The parser is a heuristic over free text a human typed under pressure. It must fail *soft*: an
address it cannot parse falls through to today's behaviour (query as written), never to an
exception — geocoding is a best-effort side lookup and must never break taking an order.
