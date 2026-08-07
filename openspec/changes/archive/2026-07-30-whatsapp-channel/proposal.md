## Why

`modules/messaging/` exists but is **schema only** — `whatsapp_contacts`,
`whatsapp_conversations` and `whatsapp_messages` with no ports, no service, no repository and
no router. Nothing writes to those tables and nothing reads them.

The restaurant already receives orders and questions over WhatsApp; today they live in
somebody's phone, invisible to the system. This change makes WhatsApp a real channel of the
product: messages land in the database, staff answer them from a shared inbox, and every
exchange is tied to the branch it arrived at.

It is deliberately **the plumbing only — answered 100% by humans, zero AI**. The WhatsApp
bridge is unofficial and can be unstable or get the number banned; this change proves it
works before the greeting automation (change 2) or the assistant (change 4) depend on it.
See `docs/messaging/ROADMAP.md` for the full program.

The existing schema also violates a binding rule: `shared/database.py:65` states every
business entity must carry `branch_id` from day 1, and all three messaging tables use only
`TenantScopedMixin`. With one WhatsApp session per branch, that is no longer survivable.

## What Changes

- **One WhatsApp session per branch.** New `whatsapp_sessions` table (branch-scoped, unique
  per branch), holding the provider instance reference and a connection lifecycle
  (`disconnected → qr_pending → connected`, plus `banned`). Session credentials stay in the
  bridge; we store status and the instance reference, never the auth material.
- **`WhatsAppGateway` port + bridge adapter.** A deliberately minimal outbound surface
  (`send_text`) modelled on nothing bridge-specific, so the adapter can be replaced when the
  bridge dies or the tenant moves to the official API.
- **Hard outbound invariant, enforced in the gateway:** nothing is sent to a phone that has
  no `whatsapp_contact` with at least one inbound message. We never initiate a conversation.
  This is what protects the number, so it is a wrapper around the port rather than a rule
  each caller remembers.
- **Idempotent inbound webhook.** `POST /webhooks/whatsapp/{instance_ref}` authenticated by
  a shared secret, resolving tenant + branch from the session. `provider_message_id` is
  unique, so the bridge's redeliveries store one message, not three.
- **Schema corrections** (dev, no data): `branch_id` on conversations and messages,
  `provider_message_id` on messages, conversation `status` becomes `new | human | closed`
  (change 2 adds `greeted` and `bot`), `sender_type` becomes `contact | employee | system`.
- **Shared inbox.** List conversations for the active branch, read a thread, send a reply.
  Claiming is an atomic conditional update (`WHERE employee_id IS NULL`) so two employees
  cannot take the same conversation; the loser is told who won.
- **Live inbox.** Inbound messages publish on the existing `EventPublisher` so open inboxes
  refetch without polling, exactly like salón and dispatch.
- **Two permissions:** `messaging.read` (see the inbox) and `messaging.attend` (claim and
  reply).

Out of scope (later changes): the automatic greeting and the store link with its token
(change 2), order status messages to the customer (change 2), alerts (change 3), and
anything involving an LLM (change 4). Also out of scope: media (images, audio, location) —
text only for now.

## Capabilities

### Added Capabilities
- `whatsapp-messaging`: per-branch WhatsApp sessions with a connection lifecycle; an
  idempotent inbound webhook that persists contacts, conversations and messages scoped to
  the receiving branch; an outbound gateway that refuses to message a contact who never
  wrote first; a shared inbox with atomic claiming and human replies; `messaging.read` /
  `messaging.attend` permission gating.
- `frontend-whatsapp-inbox`: a branch-scoped shared inbox — conversation list with unread
  state, thread view, claim, reply, close — updating live off the realtime doorbell and
  gated by the new permissions.

## Impact

- **Backend**: `modules/messaging/` gains `domain/ports.py`, `application/use_cases/`,
  `infrastructure/repositories.py`, `infrastructure/api/` and
  `infrastructure/whatsapp/` (gateway adapter + guard decorator). Migration `0021` adds
  `whatsapp_sessions`, `branch_id` on two tables, `provider_message_id`, and adjusts the
  status/sender enums.
- **New outbound dependency**: an unofficial WhatsApp bridge running as a separate service.
  It is stateful (one paired number per branch) and its credentials must persist outside the
  pod, or every redeploy forces all tenants to rescan QR codes.
- **New settings**: bridge base URL, webhook shared secret, conversation idle window.
- **Cross-module reads**: `messaging` reads `branches` (session anchor) and `employees`
  (claiming) — both already referenced by string FK in the existing models.
- **Frontend**: new inbox route, store and views; nav entry gated on `messaging.read`.
- **Operational**: three numbers, three QR pairings, three sets of bridge credentials per
  tenant. A disconnected branch is silently mute — detecting that is a change-3 alert, and
  until then it is only visible on the sessions screen.
- **Not breaking**: nothing today reads or writes these tables.
