## Context

After `whatsapp-channel`, inbound messages land in `whatsapp_conversations` /
`whatsapp_messages`, scoped to the branch whose session received them, and outbound goes
through a guarded gateway that refuses to message anyone who never wrote first.

Everything this change needs already exists:

- `business/domain/hours.py:41` — `is_open_at`, `next_opening`, pure functions over a
  branch's `operating_hours`.
- `storefront-branch-scoped` — `/store/<branch-code>`, so a greeting can send the right menu.
- Order and delivery lifecycles with the real status values found in the code: `open`,
  `closed`, `cancelled`, `pending`, `preparing`, `ready`, `assigned`, `on_route`,
  `delivered`, `in_progress`.
- `manage_storefront.py` — `find_or_create_by_phone`, so a token-less order still matches a
  customer by phone.

The economic point (see `docs/messaging/ROADMAP.md`): this change delivers what an owner
thinks of as "the WhatsApp bot" using **zero tokens**, and makes the expensive path opt-in
later.

## Goals / Non-Goals

**Goals:**
- Answer instantly, once, with the right branch's link and honest hours.
- Confirm and track an order without anyone typing.
- Never send the same automatic message twice.
- Keep automatic outbound volume low enough not to endanger the number.

**Non-Goals:**
- Understanding what the customer wrote. The greeting is unconditional; parsing intent is
  `assistant-core`.
- Conversational order taking.
- Marketing or any unsolicited send. Structurally impossible — the gateway refuses it.
- A templating engine. Placeholder interpolation only.
- Per-branch greeting text. Tenant-level, with the branch's own hours and link substituted in.

## Decisions

**1. The greeting is unconditional and fires once per conversation.**
Any inbound message on a `new` conversation gets it; the conversation moves to `greeted`. No
keyword matching, no "if the customer said hola". Trying to detect intent without a model
produces a system that is wrong in ways nobody can predict, and the greeting is cheap enough
that always sending it is correct.
*Alternative considered:* greet only on recognised greetings. Rejected — "quiero pedir" and
"buenas" and "?" all deserve the same first reply, and a keyword list is a bug farm.

**2. Dedupe lives in one table with a composite key, not in three places.**

```
  whatsapp_outbound_emissions   UNIQUE (tenant_id, dedupe_key)
    greeting:<conversation>            → once per conversation
    status:<order>:<customer_state>    → once per state per order
```

A unique constraint, an insert-or-ignore, and the send only happens if the insert won. This
is the same "emit once" shape the alerts use (`alert-notifications`) and it is the reason the
module does not become noise. Doing it with an `if last_sent_at` check is a race between two
workers.

The key is **one text column**, not the tuple `(kind, conversation_id, order_id,
customer_state)` this originally specified. In SQL two NULLs are not equal, so a status
emission — which carries no conversation — would have been unique against itself and the
message would have gone out on every bounce of the delivery. Found by the concurrency test
(3.3); the columns remain, with their FKs, for auditing and cascade deletes.
*Alternative considered:* a `greeted_at` column on the conversation and a `notified` flag per
order state. Rejected — two mechanisms for one rule, and the order flag needs a row per state
anyway.

**3. Status messages are driven by a per-tenant mapping, and the default is deliberately
short.**

```
  interno                        cliente (por defecto)
  ─────────────────────────────  ────────────────────────────────
  order open + caja abierta   →  "Pedido #142 recibido" + voucher
  item pending → in_progress  →  (nada)
  kitchen ready               →  (nada; opt-in para pickup)
  delivery preparing          →  (nada)
  delivery assigned           →  (nada; opt-in)
  delivery on_route           →  "Va en camino"
  delivery delivered          →  "Entregado"
  cancelled                   →  "Tu pedido fue cancelado"
```

Four by default. Eight would flag the number and annoy the customer; that is a product
decision expressed as a default, and tenants can opt into `ready` or `assigned`.

**4. Messaging is reached through a shared outbound port, not by importing `orders`.**
`orders`, `delivery` and `storefront` take an optional `CustomerNotifier`
(`shared/customer_channel/ports.py`) and call it after a transition they already committed.
`messaging` implements it; nothing in the core imports WhatsApp. Same shape as
`KitchenRouting` and `DeliveryDispatch`, and as `EventPublisher` living in `shared/realtime`.

*Superseded during implementation:* this decision originally said messaging would **subscribe**
to the existing realtime notifications. It cannot: those frames are browser-facing doorbells
carrying `{"kind": "status"}` and no order id, consumed per-connection by the SSE endpoint.
There is no server-side subscriber runtime to attach to, and adding one to deliver four
messages would be a second delivery system to operate. The port keeps the arrow pointing the
same way at a fraction of the cost.
*Consequence:* the notifier is best-effort **by contract** — it never raises, and every caller
swallows on top of that. A WhatsApp outage costs a status message, never a cancelled order or
a driver who cannot depart.

**5. The store token is a capability URL on the conversation, not a table.**
`store_token` + `store_token_expires_at` on `whatsapp_conversations`. Opaque, random, 24h,
renewable, reusable within its life (a customer may order twice in a day). It resolves to a
contact — never to an order — so a leaked link cannot read anyone's order history. Worst case
of a leak is a voucher delivered to the wrong person, which is why it expires.
*Alternative considered:* single-use tokens. Rejected — the customer reopens the link to order
again an hour later and it is dead, which reads as the system being broken.

**6. The token pre-fills; it does not authenticate.**
Resolving a token returns name and phone for the checkout form; the customer can still edit
them. The value is removing typing on a phone keyboard, which is where checkout conversion
dies. The order links to the contact by token when present, and falls back to
`find_or_create_by_phone` when absent or expired.

**7. Greeting text is tenant-level; the branch supplies hours and link.**
One text with placeholders (`{branch_name}`, `{menu_link}`, `{next_opening}`), rendered per
branch. Three greetings to maintain for three branches of one restaurant is a worse product
than one greeting that knows which branch it is.

**8. The assistant offer is conditional on entitlement.**
Until `assistant-core` exists, or when a tenant has not bought it, the greeting omits the
"write 1 to talk to the assistant" line and "I want to talk to someone" routes to the human
inbox. The greeting must never advertise something that will not answer.

## Risks / Trade-offs

- **Outbound volume is the ban risk.** Four messages per order is the ceiling we chose. A
  tenant that opts into every transition raises their own risk; the settings screen should
  say so plainly.
- **A lost doorbell means a missed status message.** Accepted (decision 4). Visible to staff
  in the thread, since sent messages are persisted — a gap is legible.
- **Greeting fatigue.** A regular customer who writes every day gets greeted every day,
  because the idle window closes the conversation nightly. Mitigated by the window being
  configurable; not solved.
- **Token in a link is a bearer credential.** Low stakes by construction (resolves to contact
  only, expires), but it will end up in browser history and any link preview the bridge
  generates.
- **Hours can be wrong.** If a branch's `operating_hours` are unmaintained, the greeting
  confidently states a false opening time. The data already drives the storefront, so this
  adds exposure rather than a new failure.

## Migration Plan

Alembic migration `0023_whatsapp_autoreply` (la `0022` la ocupa `order_refunds`):

- `whatsapp_conversations`: add `store_token` (nullable, unique per tenant) and
  `store_token_expires_at`; extend `status` to allow `greeted` and `bot`
- new `whatsapp_outbound_emissions` (branch-scoped): `kind`, `conversation_id` (nullable),
  `order_id` (nullable), `customer_state` (nullable), `emitted_at`, with a unique constraint
  per dedupe key
- new `whatsapp_autoreply_settings` (tenant-scoped): greeting text open/closed, assistant
  offer flag, idle window, status mapping as JSON
- `orders`: `whatsapp_contact_id` YA EXISTE (nullable FK, `ondelete SET NULL`) — nada que hacer

No backfill. Existing dev orders keep `whatsapp_contact_id` null and are simply never
messaged, which is the correct behaviour for orders whose customer never wrote to us.

## Open Questions

- **Should the voucher itemise the order or just state the total?** Itemising is friendlier
  and matches the thermal-docket idiom used elsewhere in the product, but a 15-line cart makes
  a long WhatsApp message. Leaning itemised with a line cap.
- **Does `ready` mean anything for a delivery order?** Almost certainly not — the customer
  cares about `on_route`. The mapping should probably be per fulfilment type, not just per
  tenant. Deferred until a tenant asks.
