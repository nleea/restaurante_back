# Pin the corner, not the street — resolved in the background

## Why

`Calle 41A #12C-48, Riohacha` now gets a pin. It is on the wrong corner, and the operator saw
it before the code did: *"esa calle me lo manda es para la carrera 10 más o menos, no la 12C"*.

Measured against the true intersections:

```
the pin we produce today   11.5237002, -72.9067338
Calle 41 x Carrera 10      11.5237489, -72.9064891    27 m  <- the pin is standing here
Calle 41 x Carrera 12C     11.5228503, -72.9117535   555 m  <- the address is here
```

The eyeball diagnosis was accurate to 27 metres. The cause is now understood: OSM splits a
street into many ways, a single-point geocoding query answers with **one arbitrary segment**,
and the error is bounded by the street's length. Measured across two Riohacha addresses: 90 m
for one, **3995 m** for another. That is not street-level precision, it is a lottery whose
prize is the right street.

The fix is already written in the address. `Calle 41A #12C-48` names **two** streets — Calle 41A
and Carrera 12C — and their crossing is the corner. The current geocoder parses the cross
street out and **throws it away**: it was rejected as a *fallback* (either the calle or the
carrera), and the rejection was correct — Carrera 12C's own point sits 1.48 km away. But as the
*other half of an intersection* it is the missing datum. The information was in the text all
along; nothing used it.

This matters beyond a dot on a map. The ring inference planned for dispatch divides the city
into 1.5 km bands: a pin 555 m or 4 km off the address files the delivery under the wrong ring
and sends the wrong driver.

## What Changes

- **Resolve the corner.** Query the node shared by the two named ways (`Calle 41` ∩
  `Carrera 12C`) instead of a point on one of them. Verified live: the corner comes back at
  11.5228503, -72.9117535 — the address's actual crossing.

- **A new `Overpass` lookup** alongside Nominatim. Nominatim cannot do this: asked for
  `Calle 41 & Carrera 12C` it answers with Carrera 12C's own point, and intersecting the two
  streets' bounding boxes fails because each box covers one segment, not the street.

- **The parser keeps the cross street.** `parse_street` currently returns the street and its
  base; it must also return `Carrera 12C`.

- **BREAKING (architecture): geocoding leaves the request path.** Taking an order stores the
  address and returns. A **background sweeper** resolves pins afterwards. Public Overpass
  answered in 1.6–9.1 s and **failed 1 request in 3** with a 504 during probing — that cannot
  sit inside "Abrir comanda", and it does not have to: nobody is waiting on a pin.

- **The database is the queue.** "Needs a pin" is a query —
  `latitude IS NULL AND btrim(address_text) <> ''` — not a message. No broker, no new
  dependency, idempotent, restart-safe, retries by construction, and sequential by nature,
  which is what the providers' 1 req/s policy requires. A queue with concurrent workers would
  breach it.

- **The 7 deliveries already stored without a pin get resolved for free**, since the sweeper
  cannot tell them from new ones.

- **Nominatim stays** as the fallback: no corner (a street missing from OSM, an address naming
  only one street) falls back to today's verified street-level pin, which is worse but not
  wrong.

Explicitly **out of scope**:

- **Self-hosted Overpass/Nominatim.** The right answer if delivery scales — the public instance
  is a shared free service, not infrastructure. The sweeper tolerates its flakiness, which buys
  the time to decide.
- **House-level accuracy.** `-48` is metres past the corner; OSM has no addressed buildings
  here. The corner is the ceiling, and the operator has said it is enough.
- **Re-resolving pins that are already set**, including hand-placed ones.
- **Showing "geocoding pending" in the UI.** A null pin already reads as "sin ubicación".

## Capabilities

### New Capabilities

- `delivery-geocoding-worker`: the background resolution of delivery pins — what it picks up,
  in what order, how it rate-limits, and how it fails without losing work.

### Modified Capabilities

- `delivery-management`: **Geocode a delivery address to an approximate pin** — resolves the
  intersection of the address's two streets, falling back to the street; and no longer runs
  inside the create/update call.

## Impact

**Backend only.**

- `delivery/infrastructure/address_co.py` — expose the cross street.
- `delivery/infrastructure/overpass.py` (new) — the shared-node query.
- `delivery/infrastructure/geocoder.py` — corner first, street as fallback.
- `delivery/application/use_cases/manage_delivery.py` — `create_delivery` /
  `update_delivery_address` stop awaiting a geocode.
- A sweeper entry point, plus how it is run (see design).
- `tests/` — the corner chain with a mocked transport; the sweeper's selection and rate limit.

**Risks**

- **Public Overpass failed 1 in 3 during probing.** The sweeper retries; a delivery simply
  stays pin-less until it succeeds. Acceptable precisely because it is out of the request path.
- **A pin now appears seconds after the order, not instantly.** Nothing waits on it: the map
  and the board already render a null pin as "sin ubicación".
- **`Calle 15 ∩ Carrera 10` returned two shared nodes** (18 m apart — a divided road). Any of
  them is the corner at this precision; the design picks deterministically.
