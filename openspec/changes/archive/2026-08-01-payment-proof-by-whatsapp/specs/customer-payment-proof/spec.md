## ADDED Requirements

### Requirement: A claim can be born from a chat message

An employee SHALL be able to turn an inbound chat message carrying an image or a PDF into a payment
claim for one of that contact's unsettled orders, choosing the order and confirming the amount. The
resulting claim SHALL be indistinguishable from one the customer uploaded through the order's link:
it SHALL carry the file, it SHALL be pending, and it SHALL be resolved by a person in both
directions like any other.

The system SHALL NOT create a claim on its own when a file arrives. A photograph is not a
declaration of payment: customers send pictures of streets, menus, documents and their own address,
and a claim created by arrival alone eventually becomes a "receipt" that is a photo of a dog — after
which staff learn to ignore the notice.

Creating a claim this way SHALL require the permission that registering a payment requires, not the
permission to attend conversations: it is a step on the money path.

#### Scenario: An employee turns a receipt photo into a claim

- **WHEN** an employee viewing an inbound image chooses to use it as the receipt for an unsettled
  order of that contact
- **THEN** a pending claim is created for that order, carrying that file, and the order shows it
  like any other claim

#### Scenario: The amount starts from the balance and can be corrected

- **WHEN** the employee opens the action
- **THEN** the amount is prefilled with the order's outstanding balance and can be edited before
  confirming

#### Scenario: Arrival alone creates nothing

- **WHEN** a contact with an unsettled order sends any image
- **THEN** no claim is created until a person says it is a receipt

#### Scenario: Attending is not enough

- **WHEN** a user who may attend conversations but may not register payments tries to create a claim
  from a message
- **THEN** the action is refused

#### Scenario: Only the contact's own unsettled orders are offered

- **WHEN** the employee opens the action
- **THEN** the orders offered are the ones belonging to that contact and still unsettled, and no
  other customer's order can be chosen
