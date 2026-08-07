## Context

Identity already exists but scattered: `tenant` has name/tax_id/address/phone/email; `branch` has name/address/phone/is_primary; the storefront appearance config has its own `restaurantName`/`logo_url`/`banner_url` plus a free-text hours block; `staff`/`shifts` own personnel. What's missing is (a) a structured hours model and (b) a consolidated profile that is the single source of truth. The user's decisions: **unify** identity (storefront reads one source), **reuse the logo** as the business photo, and make hours **structured**.

## Goals / Non-Goals

**Goals:**
- Structured per-branch operating hours usable to compute "open now?" and "next opening".
- A Business Profile surface consolidating existing identity + branch details + hours + staff reference.
- One source of truth for name/photo that the storefront reads.

**Non-Goals:**
- Re-implementing staff/shifts — the profile references them.
- Making hours the operational gate — the caja stays the gate ([[cash-session-operating-shift]]); hours are informational and drive the "abrimos a las X" copy.
- Duplicating tenant/branch identity into a new table — the profile aggregates them.

## Decisions

**1. Split identity: tenant-level brand vs branch-level details.**
Name, photo/logo, tax id, email = tenant (the brand, shared across branches). Address, phone, operating hours = branch (varies per location). The profile view composes both.
*Alternative considered:* one flat profile table. Rejected — it would duplicate tenant/branch and reintroduce drift, the exact problem we're removing.

**2. Structured hours = per-branch weekly windows.**
A model of (branch, weekday, open_time, close_time) rows (supporting a closed day and, if needed, split windows). Enough to compute "open now" and "next opening".
*Alternative considered:* free-form text (status quo). Rejected — can't compute "abrimos a las X".

**3. Hours inform, the caja gates.**
"Open for orders" remains "the caja is open". Hours drive the displayed next-opening time and future auto-behaviors; they do not by themselves accept/reject orders.
*Alternative considered:* hours enforce open/close. Rejected — conflicts with the established rule that opening the caja is what opens the restaurant.

**4. Unify name/photo: profile is the source, storefront reads it.**
Bind the appearance's name/logo to the business profile (reuse the logo as the photo) so there is one value. Banner stays as the cover photo.
*Alternative considered:* keep both and sync. Rejected — sync drifts; single source is cleaner.

## Risks / Trade-offs

- **Migrating the appearance's existing name/logo to read from the profile** could disturb the storefront if not done carefully → mitigation: seed the profile from current appearance/tenant values, then switch the read.
- **Timezone / overnight windows** (open past midnight) → the hours model must handle close_time < open_time; call it out in tasks and tests.
- **Multi-branch storefront** resolves a primary branch → the storefront reads that branch's hours.

## Migration Plan

1. Backend: operating-hours model + migration (seed sensible defaults or empty); business-profile read/update aggregating tenant + branch + hours; storefront exposes hours + computed next-opening; bind name/photo to the profile.
2. Frontend: "Perfil del negocio" screen (identity + branch + hours editor + staff reference); storefront closed state shows "abrimos a las X".
3. Rollback: drop hours table; revert storefront read to the appearance copy.

## Open Questions

- Structured hours granularity: single daily window vs multiple split windows (e.g. lunch + dinner)? Default: support multiple windows per day from the start (cheap now, painful later).
- Where does the profile screen live in nav (Configuración vs its own top-level "Negocio")? Default: Configuración.
- Timezone source for "abrimos a las X" — tenant/branch city vs a stored tz? Default: assume the branch's local time (Colombia) until multi-tz is needed.
