## ADDED Requirements

### Requirement: My-order view

The front SHALL expose a public route that opens the order behind an edit token and shows its
lines with their products, quantities, addons and notes, plus the order total.

The view SHALL work for anyone holding the link, without a login and without the WhatsApp
conversation — a customer who ordered from the web and never wrote on WhatsApp SHALL be able to
use it.

#### Scenario: The link opens the order

- **WHEN** a customer opens their edit link
- **THEN** they see what they ordered, with prices and total

#### Scenario: An expired link explains itself

- **WHEN** the token is expired or unknown
- **THEN** the view says the link is no longer valid and offers to contact the business, without
  revealing whether the order exists

### Requirement: Exclusions are shown as choices, not as prose

The view SHALL present each item's removable ingredients as options with the current state
already applied, and a free-text note alongside them. It SHALL NOT ask the customer to retype
the note that already exists.

#### Scenario: Current exclusions are visible

- **WHEN** an item was ordered without onion
- **THEN** the view shows "sin cebolla" already selected, alongside the other options

#### Scenario: Adding an exclusion keeps the rest

- **WHEN** the customer also excludes lettuce
- **THEN** the previous exclusion and any free-text instruction are preserved

### Requirement: What cannot be changed is visible and explained

The view SHALL make clear, per item, what can still be changed, and SHALL explain in the
customer's terms why something cannot — an item already being prepared, or an order already
ready — rather than hiding the control silently.

Removing an item, reducing a quantity and cancelling SHALL be presented as something a person
resolves, with a way to reach one.

#### Scenario: An item in the kitchen is read-only

- **WHEN** an item's preparation already started
- **THEN** its controls are inert and the view says it is already being prepared

#### Scenario: Removing points at a person

- **WHEN** the customer looks for a way to remove an item
- **THEN** the view explains that a person handles it and offers a way to write to the business

### Requirement: The amount owed is unmistakable

Before confirming an edit that raises the total, the view SHALL show the new total and the extra
amount payable, stating when it will be charged.

#### Scenario: An addition to a paid order states the difference

- **WHEN** the customer adds an item to an order they already paid
- **THEN** the view shows what they paid, the new total and the difference payable on delivery

### Requirement: A refused edit is reported truthfully

When the server refuses an edit, the view SHALL show the reason and SHALL NOT present the change
as applied.

#### Scenario: The kitchen started while the view was open

- **WHEN** the customer confirms a change the server refuses because preparation started
- **THEN** the view says so and shows the order as it actually stands
