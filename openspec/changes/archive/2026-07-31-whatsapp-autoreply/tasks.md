> Depends on `whatsapp-channel` and `storefront-branch-scoped` being applied first.

## 1. Backend — schema

- [x] 1.1 `whatsapp_conversations`: add `store_token` (nullable, `UNIQUE(tenant_id, store_token)`)
      and `store_token_expires_at`; allow `greeted` and `bot` in `status`
- [x] 1.2 New `whatsapp_outbound_emissions` (`BranchScopedMixin`): `kind`, `conversation_id`,
      `order_id`, `customer_state`, `emitted_at`; unique constraints per dedupe key
- [x] 1.3 New `whatsapp_autoreply_settings` (tenant-scoped): greeting enabled, open text,
      closed text, assistant offer flag, idle hours, token lifetime hours, status mapping JSON
- [x] 1.4 `orders`: add `whatsapp_contact_id` (nullable FK → `whatsapp_contacts`,
      `ondelete SET NULL`, indexed)
      YA EXISTÍA: presente en `OrderModel` y en la columna de Postgres desde antes de este
      change. Verificado, no se duplica.
- [x] 1.5 Mirror in domain entities; register new models in `shared/models_registry.py`
- [x] 1.6 Alembic migration `0023_whatsapp_autoreply` (0022 la ocupa `order_refunds`);
      run up/down on Postgres

## 2. Backend — template rendering

- [x] 2.1 Placeholder renderer (plain interpolation, no engine):
      `{branch_name}`, `{menu_link}`, `{next_opening}`, `{order_number}`, `{order_total}`
- [x] 2.2 Validate placeholders on save; reject unknown ones with a 422 naming the offender
- [x] 2.3 Render helper that resolves per branch: link from `branches.code`, open/closed and
      next opening from `is_open_at` / `next_opening` (`business/domain/hours.py:41`)

## 3. Backend — emit-once primitive

- [x] 3.1 `try_claim_emission(key) -> bool` — insert-or-ignore on the unique constraint,
      returning whether this caller won
- [x] 3.2 Every automatic send goes through it; the send happens only on a won claim
- [x] 3.3 Verify concurrent callers produce exactly one send (not an `if last_sent_at` check)
      DESTAPÓ UN FALLO REAL: la clave era la tupla `(kind, conversation_id, order_id,
      customer_state)` y en SQL dos NULL no son iguales, así que un aviso de estado (sin
      conversación) era único consigo mismo. Ahora la clave es una sola columna de texto
      `dedupe_key` (`greeting:<conv>` / `status:<pedido>:<estado>`); migración 0023 al día.

## 4. Backend — greeting

- [x] 4.1 On inbound to a `new` conversation: claim the greeting emission, render for the
      branch, send via the guarded gateway, move the conversation to `greeted`
- [x] 4.2 Unconditional — no keyword matching on the inbound text, including unsupported media
- [x] 4.3 Mint a `store_token` when the greeting carries the link; include it in the URL
- [x] 4.4 Omit the assistant offer when the tenant has no assistant enabled
- [x] 4.5 Skip entirely when the greeting is disabled, leaving the conversation `new`
- [x] 4.6 Add an inbox action for an agent to send the menu link manually (mints/renews the
      token the same way) — `POST /messaging/conversations/{id}/menu-link`, gated
      `messaging.attend`, firmado por el empleado

## 5. Backend — status messages

- [x] 5.1 Puerto compartido `CustomerNotifier` (`shared/customer_channel/ports.py`) en vez de
      suscripción: las notificaciones realtime son timbres sin id de pedido y no hay proceso
      consumidor. Ver design.md decisión 4 (revisada). Sin import de `orders` en `messaging`.
- [x] 5.2 Resolve the order's WhatsApp contact — by `whatsapp_contact_id`, else by phone
- [x] 5.3 Look up the tenant mapping; do nothing for unmapped transitions
- [x] 5.4 Claim the `(order, customer_state)` emission, render, send
- [x] 5.5 Ship the default mapping: received (with order number + total), on the way,
      delivered, cancelled — `ready` y `assigned` incluidos pero apagados
- [x] 5.6 Suppression (unreachable contact) never fails the triggering transition

## 6. Backend — token resolution and order linking

- [x] 6.1 `GET /storefront/session/{token}` — returns contact name, phone, branch; 404 on
      unknown or expired; exposes nothing else
- [x] 6.2 Public order intake accepts an optional token; links `orders.whatsapp_contact_id`
      when valid
- [x] 6.3 Absent, expired, unknown or branch-mismatched token → order still created, matched
      by phone, no link

## 7. Backend — settings API

- [x] 7.1 Read/write endpoints for the autoreply settings, gated on `messaging.manage`
- [x] 7.2 Defaults applied when a tenant has no row (greeting off, default mapping available
      but inactive) — GET devuelve además `default_status_mapping` y los marcadores válidos

## 8. Backend — tests

- [x] 8.1 Greeting fires once on a new conversation; further messages do not re-greet
- [x] 8.2 Greeting fires regardless of inbound content, including media placeholders
- [x] 8.3 Open branch gets the link; closed branch gets the closed variant with the real next
      opening
- [x] 8.4 Two branches of one tenant each get their own link from one tenant-level text
- [x] 8.5 Assistant offer absent without entitlement, present with it
- [x] 8.6 Greeting disabled → nothing sent, conversation stays `new`
- [x] 8.7 New conversation after the idle window is greeted again
- [x] 8.8 Emit-once: concurrent claims send exactly one; a bouncing status sends one; a
      redelivered event sends one
- [x] 8.9 Mapped transition messages; unmapped churn (`in_progress`, `preparing`, `assigned`)
      is silent
- [x] 8.10 `ready` opt-in messages for a pickup tenant
- [x] 8.11 Unreachable customer → no send, order/transition unaffected
- [x] 8.12 Token: resolves twice within its life; 404 expired; 404 unknown; returns contact
      fields only
- [x] 8.13 Tokenised order links the contact; token-less and expired-token orders still create
      and match by phone; branch-mismatched token does not link
- [x] 8.14 Placeholder validation rejects unknown placeholders

## 9. Frontend — settings screen

- [x] 9.1 Settings route gated on `messaging.manage`
- [x] 9.2 Greeting editor: enable toggle, open/closed texts, placeholder list, live preview per
      selected branch in both variants
- [x] 9.3 Status mapping editor with per-transition toggles and texts
- [x] 9.4 Typical-messages-per-order counter, with a warning past the recommended default
- [x] 9.5 Idle window and token lifetime fields, with the re-greeting explanation
- [x] 9.6 Assistant offer toggle, disabled with an explanation when not entitled

## 10. Frontend — storefront

- [x] 10.1 Read the token from the link, resolve it, pre-fill name and phone (editable)
- [x] 10.2 Carry the token through to submission; never render it in a visible field
- [x] 10.3 Unknown/expired token is ignored silently
- [x] 10.4 Confirm existing guest-profile / authenticated-user precedence still holds

## 11. Frontend — tests

- [x] 11.1 Preview renders both variants with branch substitutions
- [x] 11.2 Unknown placeholder blocks saving
- [x] 11.3 Message counter and its warning
- [x] 11.4 Offer toggle disabled without entitlement
- [x] 11.5 Checkout pre-fills from a token, stays editable, ignores an expired token
- [x] 11.6 Settings route hidden and refused without `messaging.manage`

## 12. Quality gates

- [x] 12.1 Backend: `ruff`, `mypy --strict`, full `pytest` green (+ `alembic` down/up en
      Postgres y `alembic check` sin deriva de `whatsapp_*`)
- [x] 12.2 Frontend: lint, type-check, unit tests, production build green
- [x] 12.3 Manual: write to a paired branch, receive the greeting, order from the link, receive
      the confirmation and the on-the-way message
      Probado por el dueño del proyecto el 2026-07-31 contra el despliegue: el recorrido
      completo funciona.
