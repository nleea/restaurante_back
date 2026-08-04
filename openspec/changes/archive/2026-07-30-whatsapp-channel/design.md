## Context

`modules/messaging/` has exactly two files with content: `domain/entities.py` (three
dataclasses) and `infrastructure/models.py` (three tables). No ports, no service, no
repository, no router. The tables anticipate this work — `whatsapp_conversations.status`
defaults to `'bot'` and carries a nullable `employee_id`, so a bot/human handoff was
already intended — but nothing is wired.

Two facts shape everything below:

1. **The bridge is unofficial.** No 24-hour window, no Meta template approval: we can reply
   to anything at any time. In exchange we get no delivery guarantees, a stateful pairing per
   number, and a real chance of the number being banned for behaviour that looks like bulk
   outbound.
2. **One session per branch** (decided in the roadmap). The customer picks the branch by
   picking the number, so the inbound webhook already knows the branch. Everything downstream
   — `open_order`, the caja gate, `is_open_at`, stock — is branch-scoped and fits with no
   routing logic.

`shared/database.py:65` makes `branch_id` on every business entity a binding decision. The
messaging tables violate it. We are in development with no real data, so this is a schema
edit, not a migration problem.

## Goals / Non-Goals

**Goals:**
- Persist every inbound and outbound WhatsApp message, scoped to the receiving branch.
- Let staff answer from a shared inbox without two people replying to the same person.
- Make it structurally impossible to message someone who never wrote to us.
- Prove the bridge works before any automation or AI depends on it.

**Non-Goals:**
- Any automatic reply, including the greeting (change 2).
- Order status messages and the tokenised store link (change 2).
- Any LLM (change 4).
- Media messages — text only. Images/audio/location are stored as an unsupported-type
  placeholder so the thread stays coherent, and handled later.
- Multi-number-per-branch, or one number serving several branches.
- Bridge deployment/packaging — that is infrastructure work tracked outside OpenSpec.

## Decisions

**1. The outbound invariant is a decorator around the port, not a rule in each caller.**

```
  WhatsAppGateway (port)
        ▲
        │ implements
  GuardedWhatsAppGateway ──wraps──▶ BridgeWhatsAppGateway ──HTTP──▶ bridge
        │
        └─ refuses if the contact has no inbound message
```

Every send goes through the guard, which checks the contact is *reachable* (exists and has
at least one inbound message) and refuses otherwise. Change 2 and change 4 will both send
messages; neither can bypass this by forgetting a check, because the composition root only
ever injects the guarded instance.
*Alternative considered:* check in `MessagingService.send_reply`. Rejected — later modules
send through the same gateway without going through that service, and the invariant is
exactly the thing that must not depend on discipline.

**2. `send_text` only. The port stays minimal and bridge-agnostic.**
`send_text(session_id, to_phone, body) -> provider_message_id`. No templates, no buttons, no
media, no bridge-specific options. When the bridge is replaced — and it will be — a
narrow port is a cheap adapter. Anything richer can be added when a requirement actually
needs it.

**3. Sessions store a provider reference and a status. Never credentials.**
The bridge owns the auth material and must persist it itself. We keep
`provider_instance_ref`, `status`, `phone_number` (once known) and `last_seen_at`. If we
stored credentials we would own a secret we cannot rotate and cannot use.
*Consequence:* if the bridge loses its state, our status column lies until the next status
callback or health poll. Detecting a mute branch is a change-3 alert; here it is only visible
on the sessions screen.

**4. Idempotency on `provider_message_id`, enforced by a unique constraint.**
Unofficial bridges redeliver. `UNIQUE(tenant_id, provider_message_id)` plus an
insert-or-ignore makes a redelivery a no-op rather than a duplicated message in the thread
and a duplicated notification. The webhook returns 200 on a duplicate — a 4xx would make the
bridge retry forever.

**5. Conversation continuity is an idle window, not an explicit session.**
An inbound message joins the contact's open conversation on that branch; if none is open, one
is created. A conversation closes when an agent closes it, or after `idle_window` (default 24h)
of silence, swept lazily on the next inbound message and on read. This gives change 2 a
natural "greet once per conversation" boundary without inventing a second concept.
*Alternative considered:* one conversation per contact forever. Rejected — the thread grows
unbounded and there is no natural unit to greet, assign, or close.

**6. Claiming is a conditional UPDATE, not a lock table.**

```sql
UPDATE whatsapp_conversations
   SET employee_id = :me, status = 'human'
 WHERE id = :id AND employee_id IS NULL
```

`rowcount = 0` means somebody else won, and the API answers 409 naming the holder. The claim
field already exists in the schema; a lock table would be a second source of truth for the
same fact.

**7. `status` is `new | human | closed` for now.**
Change 2 adds `greeted` and `bot`. Defining only the reachable states keeps this change
honest — a `bot` status with no bot is a lie in the data. The default changes from `'bot'` to
`'new'`.

**8. Realtime is a doorbell, consistent with the rest of the system.**
Inbound message → publish on `EventPublisher` (topic `whatsapp_inbox`, tenant+branch scope,
coarse payload) → open inboxes refetch. The publisher is best-effort and never raises, so a
broker outage degrades the inbox to polling and never loses a message: the message is already
committed before the doorbell rings.

**9. Two permissions, split read from act.**
`messaging.read` sees the inbox; `messaging.attend` claims, replies and closes. Splitting
them lets an owner watch conversations without being able to answer, and matches the
`*.read` / `*.manage` shape of the existing catalogue.

**10. Outbound messages are persisted before they are sent, then reconciled.**
Write the row, call the bridge, store `provider_message_id` on success or mark the row
`failed`. A message that vanished into a dead bridge must still be visible in the thread —
an agent needs to know their reply did not land. The alternative (send first, persist after)
loses the record exactly when it matters most.

## Risks / Trade-offs

- **The number can be banned.** Mitigated by design: never initiate, text only, organic
  volume, and no automation in this change. Not eliminated. If a number is banned the branch
  is mute until re-paired with a new number.
- **The status column can drift from reality.** We learn about disconnection from bridge
  callbacks or a poll; between the disconnect and the signal, the sessions screen shows
  `connected` for a mute branch. Change 3 turns this into an alert; here it is a known gap.
- **Re-pairing is manual and per branch.** Three QR scans per tenant, repeated whenever the
  bridge loses state. If bridge credentials are not persisted outside the pod, a redeploy
  means every tenant rescanning at once.
- **The idle window is a guess.** 24h matches how people think about a WhatsApp chat, but a
  customer who writes daily will keep re-opening conversations. Configurable, revisit with
  real usage.
- **Text-only makes some threads confusing.** A customer sending a photo of an address will
  appear as an unsupported-type placeholder. Acceptable for a first channel; the agent can
  ask for text.

## Migration Plan

Single Alembic migration `0021_whatsapp_channel`:

- create `whatsapp_sessions` (branch-scoped, `UNIQUE(tenant_id, branch_id)`)
- add `branch_id` to `whatsapp_conversations` and `whatsapp_messages` (FK → `branches`,
  `ondelete RESTRICT`, indexed, NOT NULL)
- add `provider_message_id` to `whatsapp_messages` with `UNIQUE(tenant_id, provider_message_id)`
- add `delivery_state` to `whatsapp_messages` (`pending | sent | failed`) for outbound
  reconciliation
- change `whatsapp_conversations.status` default from `'bot'` to `'new'`

No backfill: the tables are empty. `branch_id` is created NOT NULL directly rather than
nullable-then-tightened, which is only possible because there is no data — and is the whole
reason to do it now.

## Open Questions

- **Does the inbox show only the active branch or all branches the user can see?** Assumed
  active-branch-only, consistent with every other board in the product. If a small tenant
  wants one inbox for three numbers, that is a later filter, not a redesign.
- **How does the bridge report disconnection?** Callback, poll, or both depends on the
  product chosen. The session status transitions are specified; the trigger is an adapter
  detail to settle when the bridge is picked.
