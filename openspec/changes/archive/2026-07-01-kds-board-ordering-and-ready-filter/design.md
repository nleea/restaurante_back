# Design: kds-board-ordering-and-ready-filter

## Context

`sortOrdersForBoard` (front/src/lib/kds/logic.ts) currently orders: non-completed first →
severity desc → `startedAt` asc (oldest first). Ready dockets stay on the board de-emphasised.
User decision (2026-07-01): alerts keep priority, but within equal severity the newest order
shows first, and fully-ready dockets are hidden until requested via a counter toggle.

## Goals / Non-Goals

**Goals:** severity-first + newest-first ordering; ready dockets hidden by default with a
"Listas (N)" top-bar toggle (shown at the end of the grid when on); pure-logic implementation
that stays unit-testable.

**Non-Goals:** no changes to expo/my-station/rail (already exclude done work), no persistence of
the toggle, no backend involvement, no changes to bump/advance flows.

## Decisions

- **D1 — Ordering stays in `sortOrdersForBoard`**: ready-last (when visible) → severity desc →
  `startedAt` **desc**. The alert tiers already encode "old and stuck", so age-based urgency is
  not lost by flipping the base order.
- **D2 — Visibility as a pure filter**: `filterBoardOrders(orders, showReady)` in logic.ts hides
  `orderStatus === 'ready'` dockets when the toggle is off; `useKdsBoard` applies it inside
  `filteredOrders` and exposes `showReady` + `readyCount` (count of hidden-able dockets, always
  computed so the toggle label is honest even while they're hidden). Page index resets when the
  toggle flips (same as station filters).
- **D3 — Toggle in the top bar**: a "Listas (N)" pill next to the view-mode controls, ember when
  active, showing the live count; `aria-pressed` for accessibility.

## Risks / Trade-offs

- [A just-bumped docket vanishes immediately] → intended ("no mostrar hasta que se solicite");
  the toggle's count ticking up is the feedback, and the success pulse still shows for orders
  going ready on-screen when the toggle is on.
- [Newest-first buries calm-but-aging orders] → accepted deliberately: the alert ladder
  (warn → urgent → critical) pulls them back up as they age, and the late banner still shows.

## Migration Plan

Frontend-only, single commit; revert = restore previous sort/no-filter behavior.

## Open Questions

None.
