## ADDED Requirements

### Requirement: Guest profile persistence

The system SHALL persist an anonymous guest profile containing a unique token, name, address, and phone, with creation and update timestamps and an optional link to a real user account. The profile SHALL be identifiable only by an opaque UUID token; no personal data is stored in any cookie.

#### Scenario: Profile stored with generated token

- **WHEN** a guest submits contact data for the first time (no `guest_token` cookie present)
- **THEN** the system generates a new UUID token, stores a `GuestProfile` row with the submitted name/address/phone and timestamps, and returns the saved profile

#### Scenario: Token is unique and indexed

- **WHEN** a `GuestProfile` is created
- **THEN** its token SHALL be a unique, indexed UUID distinct from every other guest profile's token

### Requirement: Guest token cookie lifecycle

The system SHALL issue and read an opaque token via a dedicated `guest_token` cookie that does not collide with the real-user authentication cookie or header. The cookie SHALL be set with `httponly=True`, `secure=True`, `samesite=lax`, and a max age of one year.

#### Scenario: Cookie set on create

- **WHEN** the create/update endpoint issues a new token
- **THEN** the response SHALL set a `guest_token` cookie with `httponly`, `secure`, `samesite=lax`, and `max_age` of one year

#### Scenario: Cookie does not collide with auth

- **WHEN** a request carries both the real-user auth cookie/header and a `guest_token` cookie
- **THEN** both SHALL be readable independently and neither SHALL overwrite or shadow the other

### Requirement: Create or update guest profile

The system SHALL expose a public POST endpoint that creates a guest profile when no token cookie exists, or updates the existing profile identified by the cookie token. Inputs SHALL be validated by a Pydantic schema.

#### Scenario: Update existing profile

- **WHEN** a guest with a valid `guest_token` cookie submits new contact data
- **THEN** the system updates the existing `GuestProfile` for that token, refreshes `updated_at`, and returns the saved profile without creating a duplicate

#### Scenario: Invalid input rejected

- **WHEN** the submitted payload fails Pydantic validation
- **THEN** the system SHALL return a validation error and SHALL NOT persist the row

### Requirement: Read guest profile from cookie

The system SHALL expose a public GET endpoint that returns the guest profile identified by the `guest_token` cookie. The token SHALL be read only from the cookie, never from a query parameter or request body.

#### Scenario: No cookie present

- **WHEN** a GET request arrives without a `guest_token` cookie
- **THEN** the system SHALL return an empty/`null` profile with a success status and SHALL NOT return a 500 error

#### Scenario: Cookie present but no matching row

- **WHEN** a GET request carries a `guest_token` cookie whose token has no matching `GuestProfile`
- **THEN** the system SHALL return an empty/`null` profile cleanly

#### Scenario: Token never sourced from client input

- **WHEN** a `guest_token` is supplied via query parameter or request body instead of the cookie
- **THEN** the system SHALL ignore it and resolve the profile only from the cookie

### Requirement: Edit guest profile

The system SHALL expose a public PATCH endpoint that edits the contact fields of the guest profile identified by the `guest_token` cookie.

#### Scenario: Edit contact fields

- **WHEN** a guest with a valid `guest_token` cookie sends a PATCH with updated fields
- **THEN** the system updates only the provided fields on that guest's profile, refreshes `updated_at`, and returns the saved profile

### Requirement: Merge guest profile into user account

When a guest who has a saved profile registers or logs in as a real user, the system SHALL merge the guest profile into that user account by copying contact data to the user profile and/or linking the profile via `user_id`, so the data survives the transition to an authenticated account.

#### Scenario: Guest registers or logs in

- **WHEN** a request carries both a valid `guest_token` cookie with a saved profile and an authenticated real-user identity
- **THEN** the system SHALL associate the guest profile's contact data with the real user account (copy fields and/or set `user_id`)

#### Scenario: Authenticated precedence — no cross-session leak

- **WHEN** a user is authenticated as a real user
- **THEN** the system SHALL treat the real account as the source of truth for contact data and SHALL NOT allow the authenticated request to read or overwrite a guest profile belonging to a different session
