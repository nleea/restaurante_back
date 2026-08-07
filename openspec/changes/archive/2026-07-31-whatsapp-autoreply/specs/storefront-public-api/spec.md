## ADDED Requirements

### Requirement: Store token resolution

`GET /storefront/session/{token}` SHALL return, unauthenticated and scoped to the subdomain
tenant, the contact name and phone bound to a valid store token, together with the branch the
token was minted for. It SHALL respond 404 for an unknown or expired token, and SHALL NOT
expose orders, history, or any other customer data.

#### Scenario: A valid token resolves the contact

- **WHEN** the storefront resolves a token minted for a WhatsApp contact
- **THEN** the response carries that contact's name, phone and branch

#### Scenario: An expired token is not found

- **WHEN** the token's lifetime has passed
- **THEN** the endpoint responds 404

#### Scenario: An unknown token is not found

- **WHEN** a token matching no conversation is resolved
- **THEN** the endpoint responds 404

#### Scenario: Only contact fields are returned

- **WHEN** a token is resolved
- **THEN** the payload contains no order, no order history and no internal identifiers beyond
  what the checkout needs

### Requirement: Orders placed with a token link to the WhatsApp contact

Public order intake SHALL accept an optional store token and, when it is valid, link the
created order to the WhatsApp contact it resolves to. When the token is absent, expired or
unknown, the order SHALL still be created, matching the customer by phone as it does today.

#### Scenario: A tokenised order is linked

- **WHEN** an order is submitted with a valid token
- **THEN** the created order carries the WhatsApp contact the token resolves to

#### Scenario: A token-less order still works

- **WHEN** an order is submitted with no token
- **THEN** the order is created and the customer is matched by phone, unlinked to any WhatsApp
  contact

#### Scenario: An expired token does not block the order

- **WHEN** an order is submitted with an expired token
- **THEN** the order is created normally, matched by phone, and no link is recorded

#### Scenario: A token cannot override the branch

- **WHEN** a token minted for one branch is used on another branch's intake endpoint
- **THEN** the order is created on the branch addressed in the path, and the mismatched token
  does not link the order
