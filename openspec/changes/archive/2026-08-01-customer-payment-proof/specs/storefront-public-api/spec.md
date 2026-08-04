## ADDED Requirements

### Requirement: Public receipt upload bound to the order's edit token

The public API SHALL accept a receipt image for the order behind an edit token, with the file
travelling through the API so its type and size are checked before anything is stored.

The order SHALL come from the token and SHALL NOT be a parameter of the request. An expired,
unknown or foreign token SHALL be refused with the same answer as any other, revealing nothing
about whether the order exists.

#### Scenario: A receipt is accepted for the order behind the link

- **WHEN** a customer uploads a receipt with a valid edit token
- **THEN** the file is stored against that order and no other

#### Scenario: A file that is not an acceptable receipt is refused

- **WHEN** the upload is not an accepted image type, or exceeds the size limit
- **THEN** it is refused before being stored

#### Scenario: A dead link uploads nothing

- **WHEN** the token is expired or unknown
- **THEN** the upload is refused and nothing is stored

### Requirement: Public payment declaration by token

The public API SHALL accept a declaration that the customer paid: the amount, the method, and the
receipt already uploaded. It SHALL return the order as it stands, unchanged in money terms.

The declared amount SHALL NOT be trusted as a payment. What the response reports as owed SHALL
be the same before and after declaring.

#### Scenario: Declaring reports the order unchanged

- **WHEN** a customer declares a payment
- **THEN** the response shows the same total and the same amount owed as before

#### Scenario: The customer can see their declaration is pending

- **WHEN** the order is read after declaring
- **THEN** it reports that a declaration is awaiting confirmation

### Requirement: The checkout carries the receipt it asks for

When the public order intake receives a receipt for a method that requires proof, it SHALL record
it as a payment declaration on the created order.

#### Scenario: An attached receipt survives the order

- **WHEN** an order is created with a receipt attached
- **THEN** the created order carries a pending declaration with that receipt

#### Scenario: No receipt is still a valid order

- **WHEN** an order is created without a receipt
- **THEN** the order is created exactly as it is today
