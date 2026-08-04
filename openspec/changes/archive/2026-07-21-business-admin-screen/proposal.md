## Why

The [[business-profile-and-hours]] change shipped the data foundation — structured hours, a `GET /business/profile` read, `GET/PUT` hours, and the storefront "abrimos a las X". What's missing is the **admin surface**: a "Perfil del negocio" screen where staff actually view and edit the business identity, branch details, and operating hours (today identity is only readable, and hours are only settable via raw API). This change adds the write path and the screen.

## What Changes

- Add **`PUT /business/profile`** to edit the business identity: tenant-level fields (name, tax id, email, phone) and per-branch details (address, phone). Hours already have their own `PUT`.
- Add the **"Perfil del negocio" admin screen** (gated `menu.manage`): view/edit identity, per-branch address/phone, the weekly operating-hours editor, and the staff roster reference — consuming the existing profile + hours endpoints.
- Add a nav entry / route for it.

Out of scope (still deferred): deep identity unification (rewiring the storefront to read name/photo from the profile instead of the appearance JSON) — tracked separately; the profile already exposes those values.

## Capabilities

### Modified Capabilities
- `business-profile`: the consolidated business profile identity (tenant name/tax id/email/phone; per-branch address/phone) SHALL be editable via an authenticated update.

## Impact

- **Backend**: `BusinessService.update_profile` + `PUT /business/profile`; the repository writes tenant + branch identity fields (the one place the business module writes those tables). RBAC `menu.manage`.
- **Frontend**: a new "Perfil del negocio" view (identity form + per-branch details + hours editor + staff reference), a route, and a nav entry; consumes `GET/PUT /business/profile` and `GET/PUT /business/branches/{id}/hours`.
- **No schema change** (identity fields already exist on tenant/branch; hours table already exists).
