## Context

No object storage exists; images are `ImageUploadMock` blob URLs. No boto3/aioboto3 or python-multipart is installed — only httpx + stdlib. Cloudflare R2 is S3-compatible and supports AWS SigV4 presigned URLs. The business photo is the appearance `brand.logoUrl` (a string in the `menu_appearance` JSON), which the storefront reads.

## Goals / Non-Goals

**Goals:**
- Durable photo upload to R2, editable from the Perfil del negocio screen.
- No fragile new backend dependency; testable signing logic.
- Changing the photo in the profile reflects on the storefront (single-source the logo).

**Non-Goals:**
- Uploading banner/product images here (the same component can be reused later).
- A media library / deletion / resizing pipeline.
- Server-side file proxying (browser uploads straight to R2).

## Decisions

**1. Presigned PUT URLs signed with stdlib SigV4 (no boto3, no multipart).**
`POST /media/presign` returns `{ uploadUrl, publicUrl }`; the browser PUTs the file bytes directly to R2. Signing is pure `hashlib`/`hmac` — R2 region `auto`, service `s3`, `SignedHeaders=host`, `UNSIGNED-PAYLOAD`, short expiry (5 min).
*Alternatives considered:* (a) boto3 server-side upload — needs a new dep + python-multipart, and proxies files through the API. (b) hand-rolled multipart — same multipart gap. Presign is dep-free and the R2-standard path.

**2. The photo is single-sourced through the profile → appearance `brand.logoUrl`.**
`PUT /business/profile` accepts `photoUrl`; the business repo upserts it into the `menu_appearance` config JSON's `brand.logoUrl` (the value the storefront already reads). This does the photo half of the deferred identity unification without rewiring the storefront read path.
*Alternative considered:* the screen PATCHes the appearance directly. Rejected — the profile is the identity surface; one save is cleaner.

**3. Fail closed when R2 is unconfigured.**
With no R2 creds, `/media/presign` returns a clear error (not a broken URL). Dev without creds simply can't upload (expected); tests inject a fake/So configured test values.

**4. Key layout.** `logos/{tenant_id}/{uuid}.{ext}` — tenant-scoped, collision-free, cacheable.

## Risks / Trade-offs

- **Browser → R2 needs bucket CORS** (PUT from the app origin) → documented ops step; without it the direct upload fails with a CORS error (surfaced to the user).
- **Public read** requires the bucket public or a custom domain for `publicUrl` → `r2_public_base_url` setting.
- **SigV4 correctness** can't be end-to-end tested without live R2 → mitigate with structural + determinism + sensitivity unit tests of the signer; the real check is R2 accepting the PUT in staging.
- **Secrets**: R2 keys live in settings/env, never sent to the client (only the short-lived presigned URL is).

## Migration Plan

1. Backend: R2 settings + `shared/storage/r2.py` signer + `media` module (`POST /media/presign`) + business `photoUrl` write. Tests.
2. Frontend: `media.api.ts` + real `ImageUpload.vue` + Perfil photo control/save.
3. Ops (out of code): create the R2 bucket, set creds/env, bucket CORS + public base URL.
4. No schema change (logo lives in the existing appearance JSON).

## Open Questions

- Custom public domain vs the R2 dev `*.r2.dev` URL for `publicUrl`? Default: a configurable `r2_public_base_url`.
- Should the appearance BrandPanel also adopt the real `ImageUpload` now? Default: reuse it there in a fast follow; this change wires the profile photo.
