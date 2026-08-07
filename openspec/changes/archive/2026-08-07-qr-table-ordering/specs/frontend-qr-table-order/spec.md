## ADDED Requirements

### Requirement: The table order route is public and addressed by the QR

The frontend SHALL serve `/store/:branchCode/table/:tableCode` without authentication. It SHALL
resolve the table before rendering anything orderable, and render the branch's real public menu.

An unresolvable table SHALL render a plain dead-end that names the problem ("este código no
corresponde a ninguna mesa") rather than an empty menu or a generic error page. The diner is holding
a phone in front of a sticker; they need to know whether to call someone over or scan again.

#### Scenario: The QR opens the table's menu
- **WHEN** a diner opens the route for an active table
- **THEN** the branch's public menu renders and the table number is visible throughout

#### Scenario: A bad code says so
- **WHEN** the table code does not resolve
- **THEN** a dead-end explains that the code matches no table, and no menu or cart is shown

### Requirement: The table is stated in plain sight, never asked

The view SHALL display the resolved table number persistently, and SHALL NOT offer any control to
choose or change it.

The table is the one fact the QR exists to carry. Letting it be edited on screen would reopen
exactly the mistake the URL-scoped design prevents.

#### Scenario: The table is always visible
- **WHEN** a diner browses the menu, the cart or the confirmation
- **THEN** the table number is visible on screen at every step

#### Scenario: There is no table picker
- **WHEN** the view is rendered
- **THEN** no control allows selecting a different table

### Requirement: The diner gives a first name before building a cart

The view SHALL ask for a first name before the cart, prefilled from the guest profile when one
exists, and editable.

Prefilled because the guest cookie already exists and re-typing is friction; editable because Ana
hands her phone to Luis so he can order, and Luis's order must not say "Ana".

No phone number, no account, no login SHALL be requested to place a table order.

#### Scenario: The name is asked first
- **WHEN** a diner opens a resolved table for the first time
- **THEN** they are asked for a first name before they can confirm anything

#### Scenario: A returning diner sees their name prefilled
- **WHEN** a diner with a guest profile opens a table
- **THEN** the name field is prefilled from it and can be edited

#### Scenario: Nothing else is demanded
- **WHEN** the diner proceeds
- **THEN** no phone, e-mail, account or login is required

### Requirement: Confirming is a reviewed commitment

The view SHALL present a review step listing every line, its options and exclusions, and the total,
before the confirm action. Confirming SHALL place the order and SHALL report that it is now in the
kitchen.

The confirm button carries the whole weight of this design: it is where the diner performs the check
that staff perform for a web order, and it is the boundary between what can still be changed and
what is being cooked. It SHALL be unmistakable and SHALL NOT be reachable by accident from the menu.

#### Scenario: Review precedes confirm
- **WHEN** a diner opens the cart
- **THEN** every line, its exclusions and the total are shown before any confirm action

#### Scenario: Confirming reports it reached the kitchen
- **WHEN** a diner confirms
- **THEN** the view states that the order is in the kitchen and shows the order's label

#### Scenario: An empty cart cannot be confirmed
- **WHEN** the cart has no lines
- **THEN** the confirm action is unavailable

### Requirement: After confirming, the same screen becomes the diner's order

Once confirmed, the view SHALL become the diner's own order view, backed by the order's edit token,
from which they can add a further round or correct what the kitchen has not started.

The diner never leaves the screen they scanned into. A separate link to reopen the order would be
one more thing to lose at a table with food on it.

Reopening the QR on the same device with a live order SHALL return to that order rather than start
an empty cart.

#### Scenario: Confirming leads into the order
- **WHEN** a diner confirms their first round
- **THEN** the view shows their order with what it contains and what it costs

#### Scenario: A second round starts from the same screen
- **WHEN** the diner adds a dessert and confirms again
- **THEN** the addition is placed and shown as part of the same order

#### Scenario: Rescanning returns to the live order
- **WHEN** the same device rescans the table while its order is still open
- **THEN** the diner's existing order is shown, not an empty cart

#### Scenario: What is cooking is shown as unchangeable
- **WHEN** a line's station has already started it
- **THEN** the line is shown as no longer changeable, with the reason, and the controls are absent

### Requirement: A business that cannot serve says so before the menu

When the resolved table reports that orders cannot be taken now, the view SHALL say so before the
diner builds a cart, using the business's own words about hours ("abrimos a las …") when they apply.

Letting someone assemble a cart and refusing it at confirm wastes their time over a condition known
at the first request.

#### Scenario: Closed is said first
- **WHEN** the table resolves while the business is not taking orders
- **THEN** the view says so up front and offers no confirm action

#### Scenario: Hours are quoted when they are the reason
- **WHEN** the reason is that the business is outside its operating hours
- **THEN** the next opening is stated
