## Why

Two gaps block a polished "closed" experience and a coherent business identity. First, there is **no structured opening-hours model** — only free-text hours on the carta — so the closed-caja state can't tell a customer "abrimos a las 6pm". Second, the business's identity (name, photo, address, hours, staff) lives scattered across `tenant`, `branch`, the storefront appearance config, and the `staff` module, with the appearance holding its own copy of name/logo that can drift. The business needs one structured **Business Profile** to view/edit these details, and a single source of truth the storefront reads.

## What Changes

- Add a **structured operating-hours** model **per branch** (weekly open/close windows, per-day closed flag).
- Add a **Business Profile** admin surface consolidating **tenant identity** (name, photo/logo, tax id, email) and **branch details** (address, phone, hours), and **referencing** the existing `staff` roster (not re-implementing it).
- **Unify identity**: the profile is the source of truth for name and photo; the storefront/appearance **reads** them from it (reusing the existing logo as the business photo) instead of keeping a separate copy.
- **Enrich the storefront closed state**: the "caja cerrada" state (from [[cash-session-operating-shift]]) shows the **next opening time** computed from the structured hours ("cerrado · abrimos a las X").

Out of scope (separate proposals): the operating-shift gate itself; close-caja pending summary; per-session history.

## Capabilities

### New Capabilities
- `business-profile`: structured business identity — tenant-level brand (name, photo, tax id, email) + per-branch details (address, phone, structured operating hours) + a reference to the staff roster; the single source of truth the storefront reads.

### Modified Capabilities
- `storefront-public-api`: the public surface SHALL expose the business's structured hours and, when the caja is closed, the next opening time so the customer sees when it reopens; name/photo are sourced from the business profile.

## Impact

- **Backend**: new operating-hours model (per branch) + a business-profile read/update aggregating tenant + branch + hours; storefront reads name/photo/hours from it. Migration for the hours table; identity fields largely already exist on tenant/branch.
- **Identity unification**: the appearance config's `restaurantName`/`logo` become derived from / bound to the business profile to remove the divergent copy (decision: unify, reuse logo as the photo).
- **Frontend**: a new "Perfil del negocio" admin screen (identity + branch details + hours editor + staff reference); the storefront computes "abrimos a las X" from the hours.
- **Depends on** [[cash-session-operating-shift]] for the closed state it enriches; the hours model itself is independent and could ship first.
