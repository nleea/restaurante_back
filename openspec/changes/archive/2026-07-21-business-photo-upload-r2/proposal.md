## Why

The "Perfil del negocio" screen ([[business-admin-screen]]) shows the business photo (the logo) as a read-only preview — there is no way to change it. Image handling everywhere is the `ImageUploadMock` (ephemeral `blob:` URLs that break outside the creating tab), and there is no real object storage. The business needs a real photo upload, stored durably in Cloudflare R2, editable from the profile.

## What Changes

- Add **Cloudflare R2** object storage: SigV4 **presigned PUT URLs** generated server-side (no new backend dependency — stdlib crypto over the existing httpx). Endpoint **`POST /media/presign`** (gated `menu.manage`) returns an `uploadUrl` (the browser PUTs the file straight to R2) and the final `publicUrl`.
- **Persist the photo through the profile**: `PUT /business/profile` accepts a `photoUrl`, written into the shared appearance `brand.logoUrl` — so changing the photo in the profile is reflected on the storefront (the identity photo is now single-sourced).
- **Frontend**: a real `ImageUpload` component (presign → PUT to R2 → emit the public URL) replacing the blob mock, wired into the Perfil del negocio photo control.

## Capabilities

### New Capabilities
- `media-storage`: presigned uploads to Cloudflare R2 for business images (SigV4, direct-to-bucket).

### Modified Capabilities
- `business-profile`: the profile update SHALL accept a business photo URL and persist it as the shared brand logo.

## Impact

- **Backend**: R2 settings (account id, access key/secret, bucket, public base url); a stdlib SigV4 presign util under `shared/storage`; a small `media` module (`POST /media/presign`); the business repo writes `brand.logoUrl` into the `menu_appearance` config JSON. No new pip dependency.
- **Frontend**: `media.api.ts` (presign + PUT-to-R2 helper), a real `ImageUpload.vue`, and the Perfil screen photo control + save.
- **Ops**: the R2 bucket needs CORS allowing `PUT` from the app origin and public read (or a custom public domain) for `publicUrl`. Without R2 creds configured, `/media/presign` returns a clear "storage not configured" error.
