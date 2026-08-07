## Why

The dispatch board shows every delivery the branch has ever created — including days-old ones — because nothing ties operational entities to the cash shift. Nothing today links an order to a cash session at creation (the only link is `order_payments.cash_session_id`, set when money is received). The business needs the **open cash session to be the operating-shift boundary**: while a session is open, only its orders/deliveries/tickets are live; when it closes, they fall out of the live boards and become per-session records. This also means the restaurant is "open for orders" exactly when its caja is open — no open caja, no new orders.

## What Changes

- Add `orders.cash_session_id` (nullable FK → `cash_sessions`), **stamped at order creation** with the branch's currently open session.
- **Gate order creation at the single choke point `OrderService.open_order`**: every channel (salón/comanda, storefront, delivery) funnels through it. If the branch has no open cash session, creation is rejected with a distinct "caja cerrada" error the frontends render as a closed state; a generic message for now (enriched with opening hours in a later change).
- **Deliveries and kitchen tickets inherit** the session from their order (no own column — they resolve it via the order join).
- **Live boards scope to the open session**: dispatch (deliveries), kitchen board, and salón lists return only entities belonging to the branch's currently open cash session.
- **Retroactive rows (null `cash_session_id`) never appear on live boards** — no backfill; existing test data simply drops off the live view.

Out of scope (separate proposals): close-caja pending summary + force-close; per-closed-session history/reports; structured opening hours + business profile + the storefront "abrimos a las X" copy.

## Capabilities

### Modified Capabilities
- `order-management`: orders carry a `cash_session_id` stamped at creation; `open_order` requires an open cash session for the branch and rejects when none (all channels).
- `delivery-management`: the dispatch/deliveries listing is scoped to the branch's open cash session (via the order); null/closed-session deliveries are excluded from the live list.
- `kitchen-management`: the kitchen board is scoped to the branch's open cash session (via the order).
- `storefront-public-api`: public order intake returns a distinct "caja cerrada" rejection when the branch has no open session.
- `frontend-delivery-dispatch`: the dispatch board shows only the open session's deliveries and a clear "caja cerrada" empty state.

## Impact

- **Backend**: migration adding `orders.cash_session_id`; `OrderService.open_order` resolves the open session (reusing `CashRepository.get_open_session`) to stamp + gate; a new `CashClosedError` (→ 409) mapped in `shared/api/errors`; delivery + kitchen + salón list queries join the order's session and filter to the open one.
- **Cross-module dependency**: orders now reads the cash module's open-session resolver — a new inbound edge from `orders` → `cash` at creation (today the edge exists only at payment).
- **Frontend**: dispatch store/view render the scoped list + closed state; storefront/salón surface the "caja cerrada" rejection (basic copy).
- **No backfill**; existing orders/deliveries keep `cash_session_id = null` and are excluded from live boards.
- **Breaking (operational)**: with no open caja, order creation now fails everywhere — intended, but it means a caja must be opened before the day starts.
