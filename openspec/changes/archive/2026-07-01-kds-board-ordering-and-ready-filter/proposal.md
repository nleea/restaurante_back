# Proposal: kds-board-ordering-and-ready-filter

## Why

The pass currently surfaces the oldest work first and keeps fully-ready dockets on the board
(de-emphasised, sorted last). The kitchen wants the opposite reading: the latest order to arrive
shows first, and completed dockets leave the board entirely until someone asks for them —
otherwise they pile up as noise during service.

## What Changes

- **Board ordering**: alerted dockets (critical/urgent/warn) still float to the top — nothing
  dies silently — and within the same severity, **newest first** (latest `startedAt` on top)
  instead of oldest first.
- **Ready filter**: dockets whose components are all done are **hidden by default**. A
  "Listas (N)" toggle in the KDS top bar shows/hides them (they render at the end of the grid
  when shown). The count keeps the expeditor aware without the clutter.
- Expo panel, my-station, station rail counts, alerts and all actions are unaffected (they
  already exclude finished work).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `frontend-kitchen`: board ordering becomes severity-then-newest-first; fully-ready dockets are
  hidden behind an on-demand toggle instead of sinking to the bottom.

## Impact

- **Frontend only**: `lib/kds/logic.ts` (`sortOrdersForBoard` + a ready-visibility filter),
  `components/kds/useKdsBoard.ts` (`showReady` state, filtered orders, ready count),
  `KdsTopBar.vue` (the toggle), logic unit tests updated/added.
- No API or backend changes; no store changes.
