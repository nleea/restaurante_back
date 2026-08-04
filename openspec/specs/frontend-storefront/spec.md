# frontend-storefront

## Purpose

The public `/store` customer view (mobile-first, no auth, no El Pase chrome) consuming the public
storefront API: it themes itself from the tenant's saved appearance config, renders the tenant's real
menu (categories, products, product detail with real addons and recipe-derived removables), and its
checkout places a real order, showing the server-returned number and status.
## Requirements
### Requirement: Storefront themed by the saved appearance config

The `/store` view SHALL fetch the tenant's appearance config from the public API and apply its
theme (colors, font) as CSS variables and its block layout (flattened to a single mobile column via
`gridToLinearOrder`), instead of the mock config. It SHALL render a usable page while the config
loads and if the fetch fails (falling back to defaults), never a blank error.

#### Scenario: Real config themes the page

- **WHEN** a customer opens `/store` for a tenant with a saved config
- **THEN** the page renders in that tenant's palette/font with its configured, ordered blocks

#### Scenario: Graceful load/failure state

- **WHEN** the appearance fetch is pending or fails
- **THEN** the page shows a loading or default-themed state, not a blank screen or crash

### Requirement: Storefront renders the real menu

The `/store` carta SHALL render the tenant's real menu from the public menu endpoint — categories,
products (name, description, image, price), product detail with real available addons and
recipe-derived removable ingredients — replacing the mock carta. Search and category navigation
operate over the real data.

#### Scenario: Real products appear

- **WHEN** the menu loads
- **THEN** the carta lists the tenant's real categories and active products with their real prices
  and images

#### Scenario: Product detail shows real addons and removables

- **WHEN** a customer opens a product's detail
- **THEN** the addons and the "quitar ingredientes" list come from that product's real data (addons
  and flag-filtered recipe ingredients)

#### Scenario: Empty menu state

- **WHEN** the tenant has no published products
- **THEN** the carta shows a clear empty state rather than mock dishes

### Requirement: Checkout places a real order

The storefront checkout SHALL submit the assembled cart (line items with quantity, addons, chosen
removals, note; fulfillment type and address/GPS; customer contact) to `POST /storefront/orders`,
and the confirmation SHALL display the real order number and status returned by the API. Submission
errors SHALL be surfaced without losing the cart.

#### Scenario: Successful order shows the real number

- **WHEN** a customer completes checkout
- **THEN** the storefront POSTs the order and the confirmation shows the server-returned order
  number and initial status

#### Scenario: Submission error keeps the cart

- **WHEN** the order submission fails
- **THEN** the customer sees an error and the cart contents are preserved for retry

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

### Requirement: The checkout's receipt attachment actually sends the receipt

When the chosen payment method asks for proof, the storefront SHALL upload the attached file and
submit it with the order. It SHALL NOT present an attachment control that discards the file.

#### Scenario: The attached receipt reaches the order

- **WHEN** a customer attaches a receipt and places the order
- **THEN** the order is created carrying that receipt

#### Scenario: A failed upload is not silently swallowed

- **WHEN** the receipt cannot be uploaded
- **THEN** the customer is told, and can retry or continue without it rather than believing it was sent

### Requirement: «Mi pedido» offers to settle the difference

The view SHALL offer the same payment step the checkout uses — method and receipt — when an edit
raises what the customer owes and their method is one paid in advance, instead of only pointing
at a person.

The view SHALL present the amount **still owed**, never the order's full total, and SHALL state
that the restaurant confirms the payment.

#### Scenario: Paying the difference is reachable from the order

- **WHEN** an edit leaves an outstanding amount on a prepaid order
- **THEN** the view offers to send the receipt for what is missing

#### Scenario: The figure shown is what is missing

- **WHEN** a customer who already paid 40.000 owes 2.500 more
- **THEN** the view shows 2.500 as the amount to send, not 42.500

#### Scenario: A sent receipt is reported as pending, not as paid

- **WHEN** the customer sends the receipt
- **THEN** the view says it is awaiting the restaurant's confirmation and still shows the amount as owed

#### Scenario: Cash orders are not asked for a receipt

- **WHEN** the order is paid on delivery
- **THEN** the view says it is paid on arrival and offers no upload

### Requirement: Sending the receipt by WhatsApp is offered alongside attaching it

The view SHALL offer sending the receipt through the business's WhatsApp as an alternative to
attaching it, whenever the branch has a reachable number. Neither path SHALL be presented as
making the payment confirmed.

The WhatsApp route SHALL open the chat with a message already written, carrying the order's number
and total. Without them, the arriving file is a photograph with no context and whoever attends the
number cannot tell which order it pays or how much was owed — which is the whole reason the route
exists.

This also keeps the channel's outbound invariant intact: the customer is the one who writes first, so
nothing here initiates a conversation.

#### Scenario: Both routes are offered

- **WHEN** a customer must send a receipt
- **THEN** the view offers to attach it and to send it by WhatsApp

#### Scenario: WhatsApp remains available when the upload fails

- **WHEN** the attachment cannot be uploaded
- **THEN** the WhatsApp route is still offered

#### Scenario: No number, no dead button

- **WHEN** the branch has no phone
- **THEN** the WhatsApp route is not offered and attaching still is

#### Scenario: The chat opens with the order written in

- **WHEN** the customer takes the WhatsApp route
- **THEN** the chat opens with a message containing the order's number and total, ready to send

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

### Requirement: An unsettled prepaid order never says it is being prepared

Every customer-facing view SHALL state that the payment is being awaited, and that the order is held
until the receipt is seen, when the order was placed with a non-cash method and has no payment
registered — and SHALL NOT present such an order as being prepared. When a receipt is already pending review, the
views SHALL say that instead, so the customer is not asked twice for something already sent.

The same fact SHALL be worded from one shared place, so the checkout's confirmation and the "my
order" view cannot drift apart.

Saying "being prepared" about an order the kitchen has not seen is not a wording detail: it produces
the "is it ready yet?" question and the disappointment at the door.

#### Scenario: The confirmation states what is missing

- **WHEN** a customer confirms an order by transfer without attaching a receipt
- **THEN** the confirmation states that the payment is awaited, that the order is held, and that it
  enters the kitchen once the receipt is seen

#### Scenario: "My order" says the same thing

- **WHEN** that customer opens their order later
- **THEN** it states the same, not "being prepared"

#### Scenario: A receipt under review is distinguished

- **WHEN** the customer has already sent a receipt and it is pending
- **THEN** the views say the receipt is being reviewed, rather than asking for it again

#### Scenario: Cash and settled orders are unaffected

- **WHEN** the order is to be paid in cash, or is already settled
- **THEN** the status shown is the one shown today

### Requirement: Storefront route carries a branch code

The public storefront route SHALL accept an optional branch code segment
(`/store/:branchCode?`). When a code is present, the view SHALL load that branch's menu,
prices and hours and submit the order to that branch. When it is absent, the view SHALL
behave as today, using the tenant's primary branch.

#### Scenario: Branch link opens that branch's carta

- **WHEN** a customer opens `/store/centro`
- **THEN** the storefront shows the `centro` branch's menu, prices and open/closed state

#### Scenario: Code-less link keeps working

- **WHEN** a customer opens `/store`
- **THEN** the storefront shows the primary branch's menu exactly as before

#### Scenario: Checkout posts to the addressed branch

- **WHEN** a customer checks out from `/store/centro`
- **THEN** the order is submitted to that branch's intake endpoint

### Requirement: Unknown branch code shows a not-found state

When the addressed branch code does not resolve to an active branch, the storefront SHALL
show a clear not-found state offering the branch picker. It SHALL NOT silently load another
branch's menu.

#### Scenario: Wrong code is visible, not silent

- **WHEN** a customer opens `/store/no-existe`
- **THEN** the storefront shows a not-found state and no menu of any other branch

### Requirement: Branch picker when no branch is addressed

The storefront SHALL offer a branch picker when no branch code is present in the route and
the tenant has more than one active branch, listing those branches by name and address and
navigating to `/store/:branchCode` on selection. With a single active branch, no picker is
shown.

#### Scenario: Multi-branch tenant offers a choice

- **WHEN** a customer opens `/store` on a tenant with three active branches
- **THEN** a picker lists the branches and selecting one navigates to that branch's carta

#### Scenario: Single-branch tenant shows no picker

- **WHEN** a customer opens `/store` on a tenant with one active branch
- **THEN** the carta is shown directly with no picker

### Requirement: Cart is cleared when the branch changes

Prices, availability and variants belong to a branch, so the cart SHALL NOT be carried
across branches. When the customer moves to a different branch code with a non-empty cart,
the storefront SHALL clear the cart and tell the customer it did.

#### Scenario: Switching branch empties the cart

- **WHEN** a customer with items in the cart navigates from `/store/centro` to
  `/store/norte`
- **THEN** the cart is emptied and the customer is told the carta changed

#### Scenario: Reloading the same branch keeps the cart

- **WHEN** a customer reloads `/store/centro` with items in the cart
- **THEN** the cart is preserved

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

### Requirement: Delivery checkout communicates deferred quotation

The public storefront SHALL collect the delivery address or GPS point without displaying a fixed delivery charge or requiring a payment method. Before submission it SHALL state that the delivery cost and payment link will be confirmed by WhatsApp; after success it SHALL distinguish a pending quote from a confirmed payable total.

#### Scenario: Customer orders delivery from the public menu

- **WHEN** a customer reaches the checkout for a delivery order
- **THEN** they can submit contact, products and location without selecting a payment method or seeing the obsolete fixed fee

#### Scenario: Confirmation awaits quote

- **WHEN** a delivery order is accepted but has not yet been quoted
- **THEN** the confirmation tells the customer that the final total and payment link will arrive after the delivery value is calculated
