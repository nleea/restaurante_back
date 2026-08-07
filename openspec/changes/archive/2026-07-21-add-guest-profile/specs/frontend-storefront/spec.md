## ADDED Requirements

### Requirement: Checkout preloads guest profile

The storefront checkout SHALL, on mount, request the guest profile and preload the contact form (name, address, phone) when saved data exists, so returning anonymous customers do not retype their details. Requests to the guest-profile endpoints SHALL send credentials (`withCredentials: true` / `credentials: 'include'`) without breaking real-user auth credentials.

#### Scenario: Returning guest sees prefilled form

- **WHEN** the checkout view mounts and a saved guest profile exists for the browser's `guest_token` cookie
- **THEN** the contact form is prefilled with the stored name, address, and phone

#### Scenario: First-time guest sees empty form

- **WHEN** the checkout view mounts and no guest profile exists
- **THEN** the contact form renders empty with no error shown to the customer

### Requirement: Checkout persists guest contact data

When an anonymous customer submits the checkout, the storefront SHALL persist the entered contact data via the guest-profile create/update endpoint so it is available on the next visit.

#### Scenario: Guest submits order

- **WHEN** an anonymous customer confirms an order with contact data entered
- **THEN** the storefront calls the guest-profile create/update endpoint with credentials, persisting the name, address, and phone

### Requirement: Authenticated user data takes precedence

When a real user is authenticated, the storefront SHALL use their account contact data as the source of truth and SHALL NOT overwrite the form from the guest profile.

#### Scenario: Logged-in user checks out

- **WHEN** the checkout view mounts and the frontend auth store reports an authenticated real user
- **THEN** the form is populated from the user's account data and the guest profile is not used to override it
