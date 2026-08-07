## 1. Backend — R2 storage

- [x] 1.1 Add R2 settings (account id, access key id, secret, bucket, public base url) to config; a derived `is_configured`
- [x] 1.2 `shared/storage/r2.py`: stdlib SigV4 presigned PUT (`presign_put(key, content_type, now, expires)`) + `public_url(key)` + `is_configured`
- [x] 1.3 Unit tests for the signer: structure (host/path/query params), determinism, key/secret sensitivity, public_url

## 2. Backend — media endpoint

- [x] 2.1 `media` module: `POST /media/presign` (gate `menu.manage`) → `{ uploadUrl, publicUrl }`; key `logos/{tenant}/{uuid}.{ext}`; validate image content-type
- [x] 2.2 Return a clear error when R2 is not configured
- [x] 2.3 Tests: presign returns url shape (with test creds); unconfigured → error; RBAC gate

## 3. Backend — profile photo

- [x] 3.1 `PUT /business/profile` accepts `photoUrl`; business repo upserts it into `menu_appearance` config `brand.logoUrl`
- [x] 3.2 Tests: setting photo via profile writes the appearance logo; profile read reflects it

## 4. Frontend

- [x] 4.1 `media.api.ts`: `presignUpload(filename, contentType)` + `uploadToR2(uploadUrl, file)` helper
- [x] 4.2 Real `ImageUpload.vue` (pick → presign → PUT to R2 → emit public URL; loading/error states)
- [x] 4.3 Perfil del negocio: photo control uses `ImageUpload`; include `photoUrl` in the profile save
- [x] 4.4 Frontend tests: media api (presign + PUT); component emits the public URL on success

## 5. Validation

- [x] 5.1 Backend tests + ruff + mypy
- [x] 5.2 Frontend type-check, unit tests, lint, build
- [x] 5.3 `openspec validate business-photo-upload-r2 --strict` passes
