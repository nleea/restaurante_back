## 1. Parse the nomenclature

- [x] 1.1 Add an address parser to `delivery/infrastructure/geocoder.py` that pulls the street out of Colombian nomenclature: type + number + optional letter (`Calle 41A #12C-48` → `Calle 41A`), dropping the house number from the query only
- [x] 1.2 Recognise the common spellings and canonicalise the type: `calle/cll/cl` → `Calle`; `carrera/cra/kra/krr/kr/k` → `Carrera`; plus `avenida/av`, `diagonal/diag/dg`, `transversal/transv/tv`
- [x] 1.3 Fail soft: an address the parser does not understand falls through to the address as written (today's behaviour), never to an exception — geocoding must never break taking an order
- [x] 1.4 Unit-test the parser alone (no network): the real failing address, abbreviations, missing house number, extra spacing, unparseable input

## 2. Verify the match

- [x] 2.1 Compare the result's `address.road` against the street asked for (case-insensitive, trimmed); a mismatch is a miss. `addressdetails=1` is already requested, so no extra call
- [x] 2.2 A result with no `road` at all (a suburb or POI match) is unverifiable → miss
- [x] 2.3 Verification applies only when the parser produced a street; a raw fall-through query keeps today's trust-the-top-hit behaviour (there is no street to compare against)

## 3. The candidate chain

- [x] 3.1 Try the street; if unverified and it carries a letter suffix, retry the base street (`Calle 41A` → `Calle 41`). Two attempts maximum — public Nominatim allows 1 req/s
- [x] 3.2 Do NOT add a cross-street candidate. Measured 1.48 km from the real street with `ring_step_km = 1.5` — a whole ring band, and it verifies cleanly, so nothing downstream could catch it (see design §3)
- [x] 3.3 No verified candidate → return None, the pin gets placed by hand
- [x] 3.4 Keep caching keyed on the caller's address + bias, so a repeat address (hit or miss) costs zero requests; keep transient failures bypassing the cache

## 4. Tests (mocked transport, no network)

- [x] 4.1 `Calle 15 #10-20` → queries the street without the house number and resolves
- [x] 4.2 A response whose `address.road` names another street → no location (the confident-wrong-pin case that started this)
- [x] 4.3 `Calle 41A` unverified → retries `Calle 41` → resolves; assert exactly two transport calls
- [x] 4.4 Neither candidate verifies → no location, and Carrera 12C is never queried
- [x] 4.5 Unparseable address → queried as written, no raise
- [x] 4.6 A repeated address does not re-hit the transport (cache), and a transient failure still bypasses the cache
- [x] 4.7 Run `poetry run pytest`, `poetry run ruff check .` and `poetry run mypy src` green

## 5. Verify against live Nominatim

- [x] 5.1 Drive the real adapter against public Nominatim with the address that failed for real — `calle 41A #12C - 48, Riohacha` — and confirm it now yields a verified pin via `Calle 41`, not the `Calle 44` house
- [x] 5.2 Re-check the addresses that already worked (`Calle 15 #10-20`, `Carrera 7 #12-30`) still resolve — this change must not regress them
- [x] 5.3 Confirm a wrong-street match is rejected end-to-end rather than stored
- [x] 5.4 Keep these as scratchpad probes, NOT as tests: the suite must not depend on the network or on OSM data drifting (see proposal → Impact)

## 6. Prove it through the real flow

- [x] 6.1 Create a delivery through the API with `calle 41A #12C - 48, Riohacha` against the running backend and confirm the stored record keeps the full address AND now carries a pin
- [x] 6.2 Confirm the pin lands near Calle 41 (not on Calle 44, not on Carrera 12C ~1.5 km away)
