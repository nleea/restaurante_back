## 1. Backend — schema

- [x] 1.1 Add `WhatsAppSessionModel` (`BranchScopedMixin`, `TimestampMixin`):
      `provider_instance_ref` (unique per tenant), `status`, `phone_number`, `last_seen_at`;
      `UNIQUE(tenant_id, branch_id)`
- [x] 1.2 Switch `WhatsAppConversationModel` and `WhatsAppMessageModel` to
      `BranchScopedMixin` (satisfies the binding rule in `shared/database.py:65`)
- [x] 1.3 Add `provider_message_id` to `WhatsAppMessageModel` with
      `UNIQUE(tenant_id, provider_message_id)`, and `delivery_state`
      (`pending | sent | failed`)
- [x] 1.4 Change `WhatsAppConversationModel.status` default from `'bot'` to `'new'`
- [x] 1.5 Mirror all of it in `messaging/domain/entities.py` (add `WhatsAppSession`)
- [x] 1.6 Alembic migration `0021_whatsapp_channel`; `branch_id` created NOT NULL directly
      (no data exists); run up/down on Postgres
- [x] 1.7 Register the new model in `shared/models_registry.py`

## 2. Backend — ports

- [x] 2.1 `messaging/domain/ports.py`: `MessagingRepository` (sessions, contacts,
      conversations, messages, claim, reachability)
- [x] 2.2 `WhatsAppGateway` port: `send_text(session_id, to_phone, body) -> str` only —
      no templates, no media, nothing bridge-specific
- [x] 2.3 Domain errors: `SessionNotFoundError`, `ConversationAlreadyClaimedError` (→ 409),
      `ContactNotReachableError`; map them in `shared/api/errors.py`

## 3. Backend — the outbound invariant

- [x] 3.1 `BridgeWhatsAppGateway` in `infrastructure/whatsapp/` — HTTP adapter for the bridge
- [x] 3.2 `GuardedWhatsAppGateway` decorator implementing the same port: refuses when the
      contact has no inbound message, raising `ContactNotReachableError`
- [x] 3.3 Composition root injects **only** the guarded instance — verify no wiring exposes
      the raw adapter
- [x] 3.4 Repository method `is_reachable(tenant_id, phone) -> bool` (contact exists AND has
      ≥1 inbound message)

## 4. Backend — inbound webhook

- [x] 4.1 `POST /webhooks/whatsapp/{instance_ref}`, shared-secret header, no user auth
- [x] 4.2 Resolve tenant + branch from the session; reject unknown instance refs
- [x] 4.3 Find-or-create contact by phone within the tenant
- [x] 4.4 Resolve the open conversation for (contact, branch) or open one; close and replace
      when past the idle window
- [x] 4.5 Insert the message idempotently on `provider_message_id`; respond 200 on duplicates
- [x] 4.6 Store unsupported media types as a placeholder message so the thread stays coherent
- [x] 4.7 Publish the `whatsapp_inbox` doorbell (tenant + branch) after commit, best-effort

## 5. Backend — inbox use cases

- [x] 5.1 `list_conversations(tenant, branch)` — open conversations with last-message preview
      and claim state
- [x] 5.2 `get_thread(tenant, branch, conversation_id)`
- [x] 5.3 `claim(conversation_id, employee_id)` — conditional UPDATE
      `WHERE employee_id IS NULL`; `rowcount = 0` → `ConversationAlreadyClaimedError` naming
      the holder
- [x] 5.4 `send_reply(...)` — persist `pending` → call gateway → mark `sent` with the
      provider id, or `failed`
- [x] 5.5 `close(conversation_id)`
- [x] 5.6 Session use cases: list, start pairing, apply provider status updates

## 6. Backend — API and permissions

- [x] 6.1 Router + schemas for inbox and sessions under `messaging/infrastructure/api/`
- [x] 6.2 Add `messaging.read`, `messaging.attend`, `messaging.manage` to
      `identity/domain/permissions_catalog.py`
- [x] 6.3 Gate every endpoint; the webhook stays secret-authenticated with no permission
- [x] 6.4 Register the router in the app factory

## 7. Backend — settings

- [x] 7.1 `whatsapp_bridge_base_url`, `whatsapp_webhook_secret`,
      `whatsapp_conversation_idle_hours` (default 24) in `shared/config.py`
- [x] 7.2 Document that bridge credentials live in the bridge and must persist outside the
      pod, or every redeploy forces all tenants to rescan QR

## 8. Backend — tests

- [x] 8.1 Webhook: message lands on the session's branch, not the primary branch
- [x] 8.2 Webhook: same `provider_message_id` three times → one message, 200 each time
- [x] 8.3 Webhook: unknown instance ref and wrong secret both persist nothing
- [x] 8.4 Contact reused by phone; same phone on two branches → one contact, two
      conversations
- [x] 8.5 Idle window: message within the window joins; past it opens a new conversation
- [x] 8.6 **Guard**: send to a phone with no contact, and to a contact with no inbound
      message, are both refused and transmit nothing
- [x] 8.7 Guard cannot be bypassed — the wired gateway is the guarded one
- [x] 8.8 Concurrent claim: exactly one succeeds, the other gets 409 naming the holder
- [x] 8.9 Reply persists `pending` first; bridge failure leaves it `failed` and visible
- [x] 8.10 Doorbell published on inbound; a failing publisher does not fail the webhook
- [x] 8.11 Permission gating: read/attend/manage each refused without their permission, and
      `messaging.read` alone cannot claim, reply or close

## 9. Frontend — inbox

- [x] 9.1 Inbox route + store, scoped to the active branch
- [x] 9.2 Conversation list: contact, preview, time, claim state, empty state
- [x] 9.3 Thread view distinguishing contact / employee / system, with failed-reply state
- [x] 9.4 Reply composer, gated on `messaging.attend`
- [x] 9.5 Claim and close actions; losing a claim shows who holds it and refreshes the list
- [x] 9.6 Subscribe to the `whatsapp_inbox` doorbell with the polling fallback

## 10. Frontend — sessions

- [x] 10.1 Sessions screen: per-branch status and paired number, gated on `messaging.manage`
- [x] 10.2 Start pairing and render the QR; reflect `qr_pending` → `connected`
      Evolution API v2.3.7: pairing crea la instancia, registra el webhook y pide el QR
      (`GET /instance/connect` → base64), que se pinta en la pantalla.
- [x] 10.3 A disconnected branch is clearly marked as not receiving messages

## 11. Frontend — tests

- [x] 11.1 Inbox lists only the active branch and reloads on branch change
- [x] 11.2 Reply appears attributed; failed reply visible
- [x] 11.3 Losing a claim is explained, not silent
- [x] 11.4 Read-only user sees threads with claim/reply/close unavailable
- [x] 11.5 Routes hidden and refused without their permissions

## 12. Quality gates

- [x] 12.1 Backend: `ruff`, `mypy --strict`, full `pytest` green
- [x] 12.2 Frontend: lint, type-check, unit tests, production build green
- [x] 12.3 Manual: pair one branch against a real bridge, send a message in, reply out
      Verificado contra Evolution API v2.3.7 (whp.wsquote.uk): sesión vinculada, mensajes
      entrantes persistidos y TRES respuestas salientes en `sent`. El contacto quedó como
      `196125537607835@lid` — el caso que hacía fallar todos los envíos, ya corregido.
