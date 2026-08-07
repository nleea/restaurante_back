# media-storage Specification

## Purpose
TBD - created by archiving change business-photo-upload-r2. Update Purpose after archive.
## Requirements
### Requirement: Presigned R2 uploads for business images

The system SHALL issue short-lived presigned PUT URLs for uploading business images directly to Cloudflare R2, via an authenticated endpoint, returning both the upload URL and the final public URL. Signing uses AWS SigV4; R2 credentials never reach the client.

#### Scenario: Presign an upload

- **WHEN** an authorized user requests a presigned upload for an image filename/content-type
- **THEN** the system returns an `uploadUrl` (a SigV4 presigned PUT valid briefly) and the `publicUrl` the object will have

#### Scenario: Storage not configured

- **WHEN** a presign is requested but R2 is not configured
- **THEN** the system returns a clear error and no URL

#### Scenario: Unauthorized presign rejected

- **WHEN** a user without `menu.manage` requests a presigned upload
- **THEN** the request is rejected

