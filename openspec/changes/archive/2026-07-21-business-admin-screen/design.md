## Context

`business-profile-and-hours` shipped: the `business` module (structured hours model + helpers), `GET /business/profile` (aggregates tenant identity + branches + hours + staff count), `GET/PUT /business/branches/{id}/hours`, and the public `GET /storefront/hours`. Identity is read-only and there is no admin screen. This change adds the identity write and the "Perfil del negocio" screen.

## Goals / Non-Goals

**Goals:**
- Edit the business identity (tenant name/tax id/email/phone; per-branch address/phone).
- A single admin screen to manage identity + branch details + hours + see staff.

**Non-Goals:**
- Deep identity unification (storefront reading name/photo from the profile) — still deferred.
- Editing staff here (the screen references the existing staff module).
- Photo/logo upload (uses the existing appearance logo as the photo).

## Decisions

**1. `PUT /business/profile` writes tenant + branch identity in one call.**
Payload carries the tenant fields and a list of per-branch `{id, address, phone}`. The business repo updates `tenants` and `branches` rows directly — the one deliberate place the business module writes those tables (mirroring how it already reads them for the profile).
*Alternative considered:* separate tenant-edit and branch-edit endpoints in identity. Rejected — no such endpoints exist, and the profile is the natural admin surface; keeping it in one place matches the screen.

**2. Hours edited via the existing `PUT /business/branches/{id}/hours`.**
The screen's hours editor replaces a branch's whole week (the endpoint is already a full replace). v1 UI: per weekday, closed or a single open/close window; the model already supports split windows for a later enhancement.

**3. Screen gated `menu.manage`, same as the appearance editor.**
The same admin who edits the public carta owns the business identity/hours.

## Risks / Trade-offs

- **Editing tenant/branch from the business module** crosses into identity's tables → Mitigation: writes are narrow (identity fields only), validated, and this is already the module that reads them for the profile.
- **Hours editor UX for split windows** → v1 handles the common single-window-per-day case; multiple windows are a noted enhancement (the backend already supports them).

## Migration Plan

1. Backend: `update_profile` use case + repo writes + `PUT /business/profile` + tests.
2. Frontend: "Perfil del negocio" view + route + nav entry; identity/branch forms + hours editor; consume the endpoints.
3. No schema/data migration.

## Open Questions

- Where in nav does it live — Configuración vs a top-level "Negocio"? Default: Configuración.
