## Why

`whatsapp-channel` makes WhatsApp a real channel, but every reply is typed by a person. Three
things a restaurant needs are mechanical and should never wait for staff — or for an LLM:

1. **Somebody writes and nobody answers for twenty minutes.** The first reply should be
   instant: here is the menu link, here are our hours, or "we open at 6".
2. **A customer who orders on the web gets no confirmation.** The order exists in the system
   and is invisible to the person who placed it.
3. **Nobody knows their order is on the way.** Staff field "¿ya salió?" by hand.

None of this needs a model. The greeting, the link, the hours, the voucher and the status
updates are deterministic text over data the system already has — `is_open_at` /
`next_opening` (`business/domain/hours.py:41`) and the order/delivery lifecycle. This change
is the piece a restaurant owner actually shows off, and it costs zero tokens.

It also introduces the mechanism that ties a web order back to the person who wrote on
WhatsApp: the link carries an opaque token, so the voucher can be delivered and the checkout
can pre-fill the phone the customer is already writing from. See `docs/messaging/ROADMAP.md`.

**Depends on `whatsapp-channel` (sessions, gateway, conversations) and
`storefront-branch-scoped` (the per-branch link this change sends).**

## What Changes

- **Conversation states for automation.** `greeted` and `bot` join `new | human | closed`.
  An inbound message on a `new` conversation triggers the greeting once; the conversation
  becomes `greeted` and never greets again while it stays open.
- **A configurable greeting per tenant**, aware of the branch's hours: open → the menu link;
  closed → the link plus the real next opening time from `next_opening`. The greeting offers
  the assistant only when the tenant has it enabled (it does not exist until `assistant-core`).
- **The greeting never initiates.** It is a reply, so the channel's outbound invariant already
  holds. Nothing in this change can start a conversation.
- **A tokenised store link.** Sending the link mints an opaque `store_token` on the
  conversation (default 24h, renewable, reusable within its life). A public endpoint resolves
  it to the contact's name and phone so the checkout pre-fills them, and the resulting order
  is linked to the WhatsApp contact.
- **Order status messages.** Each transition maps to a customer-facing message through a
  **per-tenant mapping**, because a pickup-only restaurant wants `ready` and a delivery-only
  one never does. Default mapping sends four: received (with the voucher), on the way,
  delivered, cancelled. Internal churn (`pending → in_progress`, `preparing`, `assigned`)
  sends nothing.
- **Every automatic message is emitted once.** Greeting deduped per conversation; status
  messages deduped on `(order, customer_state)`, so a `confirmed → waiting → confirmed`
  bounce or a retry does not message the customer twice.
- **Messages are only sent to reachable contacts.** A web order from someone who never wrote
  on WhatsApp is silently not messaged — the channel's invariant, unchanged.
- **A settings screen** for the greeting text, the hours-closed variant, the idle window and
  the status mapping.

Out of scope: alerts to staff (`alert-notifications`), anything involving an LLM
(`assistant-core`), media messages, and conversational order taking.

## Capabilities

### Added Capabilities
- `whatsapp-autoreply`: conversation states `greeted`/`bot`; a per-tenant, hours-aware
  greeting emitted once per conversation; a tokenised per-branch store link minted on the
  conversation; per-tenant mapping of order/delivery transitions to customer messages, each
  emitted at most once; all of it strictly reply-only and LLM-free.
- `frontend-whatsapp-settings`: a per-tenant screen to edit the greeting (open and closed
  variants), toggle the assistant offer, set the conversation idle window, and choose which
  order transitions message the customer.

### Modified Capabilities
- `storefront-public-api`: a public endpoint resolves a store token to the contact's name and
  phone; orders placed with a valid token are linked to the originating WhatsApp contact.
- `frontend-storefront`: the checkout pre-fills name and phone from the token in the link and
  carries it through to order submission.

## Impact

- **Backend**: new `whatsapp-autoreply` use cases inside `modules/messaging/`; a
  `MessageTemplate` renderer (plain interpolation, no templating engine); tenant-level
  autoreply settings; `store_token` + expiry on `whatsapp_conversations`; a
  `whatsapp_outbound_emissions` table carrying the dedupe keys for greeting and status
  messages; `orders.whatsapp_contact_id` (nullable) for the token-linked orders.
- **Cross-module reads**: messaging now observes order and delivery transitions. Wired
  through the existing realtime/event path rather than a direct import, so `orders` does not
  learn about WhatsApp.
- **New settings**: default greeting text, default status mapping, token lifetime.
- **Frontend**: settings screen; checkout pre-fill; nothing new in the inbox beyond system
  messages already rendering.
- **Operational**: this is the first outbound volume the number will see. The default mapping
  is deliberately four messages per order, not eight — that ceiling is the main defence
  against the bridge's number being flagged.
- **Not breaking**: with the mapping empty and the greeting disabled, behaviour is exactly
  `whatsapp-channel`.
