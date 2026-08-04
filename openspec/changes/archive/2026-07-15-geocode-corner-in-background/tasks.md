## 1. The cross street stops being thrown away

- [x] 1.1 `address_co.parse_street` returns the cross street too (`Calle 41A #12C-48` → cross `Carrera 12C`), inverting the type: a Calle's cross is a Carrera and vice versa
- [x] 1.2 The cross street gets the same base-street treatment (`12C` → `12`) for its own fallback
- [x] 1.3 Unit-test the cross extraction alongside the existing parser tests — no network

## 2. Overpass: the shared node

- [x] 2.1 New `delivery/infrastructure/overpass.py`: given two street names and a city, return the node shared by the two named ways
- [x] 2.2 Use the **area-scoped** query, not bbox — bbox 504'd every time in probing while area answered (design §1)
- [x] 2.3 Several shared nodes (a divided road: `Calle 15 ∩ Carrera 10` returned two, 18 m apart) → take the first by node id, deterministically
- [x] 2.4 Resolve the city once from the branch's business pin (reverse geocode) and cache it — branch settings hold coordinates, not a city
- [x] 2.5 Same failure discipline as the Nominatim adapter: a transient failure raises `_LookupFailed` (not cached), a genuine no-match returns None
- [x] 2.6 Injectable transport, so tests never touch the network

## 3. The chain

- [x] 3.1 Corner first: `street ∩ cross`, then `base_street ∩ cross` — the letter-suffix fallback carries into the intersection (this is the user's actual address: `Calle 41A ∩ Carrera 12C` misses, `Calle 41 ∩ Carrera 12C` hits)
- [x] 3.2 No corner → fall back to today's verified street-only Nominatim pin. Keep it: worse is not wrong, and it beats nothing
- [x] 3.3 Never resolve to the cross street alone (1.48 km away — design §2 of the previous change, still true)
- [x] 3.4 Keep caching keyed on the caller's address + bias, so a repeat address costs zero requests

## 4. Geocoding leaves the request path

- [x] 4.1 `create_delivery` stores the address and returns — no awaited geocode
- [x] 4.2 `update_delivery_address` clears the pin when the address changes and no explicit pin is given, so the record re-enters the sweeper's set; an explicit pin is always preserved
- [x] 4.3 Delete `_geocode_address` from the create/update path and its now-dead wiring
- [x] 4.4 **Do this LAST** (design → Migration): until the sweeper runs, this leaves new deliveries pin-less indefinitely

## 5. The sweeper

- [x] 5.1 `scripts/geocode_pending.py`: select up to N records where `latitude IS NULL AND btrim(address_text) <> ''`, resolve each, write the pin back, exit
- [x] 5.2 Sequential with a pause between provider calls — the loop IS the rate limiter (design §5)
- [x] 5.3 Derive tenant, branch and bias from each record; a branch with no business pin resolves unbiased rather than being skipped
- [x] 5.4 Never touch a record that already has a location
- [x] 5.5 A provider failure on one record must not abort the pass — log and move on
- [x] 5.6 Log what the pass did (found / resolved / failed), so a scheduled run is observable

## 6. Tests (mocked transports, no network)

- [x] 6.1 Parser: the cross street comes out of the real failing address
- [x] 6.2 Overpass adapter: shared node parsed; several nodes → first by id; empty → None; 504 → `_LookupFailed`
- [x] 6.3 Chain: `Calle 41A ∩ Carrera 12C` misses → `Calle 41 ∩ Carrera 12C` hits → the corner is returned, and Nominatim is never called
- [x] 6.4 Chain: no corner → falls back to the Nominatim street pin
- [x] 6.5 `create_delivery` does not call any geocoder and returns with a null pin
- [x] 6.6 `update_delivery_address` clears the pin on an address change; an explicit pin survives
- [x] 6.7 Sweeper: picks only pin-less records with an address; skips located ones; a failure on one record does not abort the pass; each record is biased to its own branch
- [x] 6.8 Run `poetry run pytest`, `poetry run ruff check .` and `poetry run mypy src` green

## 7. Verify against live services

- [x] 7.1 Resolve `Calle 41A # 12C-48, Riohacha, La Guajira` through the real chain and confirm the pin lands on `Calle 41 ∩ Carrera 12C` (11.5228503, -72.9117535) — NOT the Carrera 10 corner 555 m away that the operator spotted
- [x] 7.2 Re-check `Calle 15 #10-20` and `Carrera 7 #12-30`: `Carrera 7 ∩ Calle 12` should now resolve the corner instead of a segment 3995 m off
- [x] 7.3 Confirm an address whose streets are not in OSM still falls back to the street pin
- [x] 7.4 Keep these as scratchpad probes, NOT tests — the suite must not depend on the network or on OSM drifting

## 8. Prove the whole loop

- [x] 8.1 Create a delivery through the API with the real address; confirm it returns immediately with a null pin and the caller was not blocked
- [x] 8.2 Run the sweeper; confirm the record gains the corner pin
- [x] 8.3 Confirm the pass also resolves the pin-less deliveries already in the database (7 at last count), without being told about them
- [x] 8.4 Run the sweeper twice; confirm the second pass finds nothing to do and touches nothing
