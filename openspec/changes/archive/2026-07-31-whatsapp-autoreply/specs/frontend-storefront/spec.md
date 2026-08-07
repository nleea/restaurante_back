## ADDED Requirements

### Requirement: Checkout pre-fills from the store token

The storefront SHALL read a store token from the link, resolve it, and pre-fill the checkout's
name and phone with the contact it returns. The customer SHALL still be able to edit both. An
unknown or expired token SHALL be ignored silently, leaving the checkout empty as it is today.

#### Scenario: Arriving from WhatsApp pre-fills contact data

- **WHEN** a customer opens a store link carrying a valid token
- **THEN** the checkout's name and phone are pre-filled with that contact's data

#### Scenario: Pre-filled data stays editable

- **WHEN** the customer changes the pre-filled name or phone
- **THEN** the order is submitted with the edited values

#### Scenario: An expired token is invisible to the customer

- **WHEN** the token in the link has expired
- **THEN** the storefront shows the normal empty checkout with no error

### Requirement: The token rides through to order submission

The storefront SHALL carry the token from the link through to the order submission so the
resulting order is linked to the WhatsApp contact. It SHALL NOT display the token or place it
in any user-visible field.

#### Scenario: The order carries the token

- **WHEN** a customer checks out from a tokenised link
- **THEN** the submission includes the token

#### Scenario: The token is not shown

- **WHEN** the checkout is rendered from a tokenised link
- **THEN** the token appears in no visible field

#### Scenario: Guest profile precedence is unchanged

- **WHEN** a token pre-fills contact data and an authenticated user's data also applies
- **THEN** the existing precedence rules decide which wins, unchanged by this capability
