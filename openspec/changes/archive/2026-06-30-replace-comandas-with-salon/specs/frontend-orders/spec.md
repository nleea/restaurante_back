## REMOVED Requirements

### Requirement: Orders route is permission-gated

**Reason**: The standalone "Comandas" screen is replaced by the Salón floor screen. The `/orders`
route and "Comandas" nav entry are removed; `/orders` now redirects to `/floor`.
**Migration**: See `frontend-salon` → "Salón route is permission-gated". The same `orders.read`
gating and mutation-permission model apply on `/floor`, and `/orders` redirects there.

The system SHALL expose an `/orders` route that requires authentication and the `orders.read` permission, and SHALL surface a "Comandas" navigation entry only when the user holds `orders.read`. Mutating controls SHALL be gated by their backend permissions (`orders.create` for opening orders / adding items / creating tables, `orders.update` for quantity / discount / close, `orders.cancel` for cancellation). This gating is UX; the backend enforces authorization independently.

#### Scenario: Authorized user reaches the comandas screen

- **WHEN** an authenticated user with `orders.read` navigates to `/orders`
- **THEN** the comandas screen renders and the "Comandas" nav entry is visible

#### Scenario: Unauthorized user is blocked

- **WHEN** an authenticated user without `orders.read` navigates to `/orders`
- **THEN** the router redirects to the Forbidden view and the "Comandas" nav entry is hidden

### Requirement: List open orders

**Reason**: The open-orders master list is replaced by the floor grid, where occupied tables (and the
delivery list) are the open orders.
**Migration**: See `frontend-salon` → "Live floor grid backed by real tables and orders". Occupied
tables surface their open order and total; selecting one opens its ticket.

The screen SHALL list the active branch's orders, defaulting to open ones, and let the user open any into its ticket.

#### Scenario: List open orders

- **WHEN** the orders list loads
- **THEN** the active branch's open orders are listed and selectable
