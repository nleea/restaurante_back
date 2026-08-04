# Tasks: kds-board-ordering-and-ready-filter

## 1. Logic

- [x] 1.1 `lib/kds/logic.ts`: `sortOrdersForBoard` → ready-last (when visible), severity desc,
      then `startedAt` DESC (newest first); add `filterBoardOrders(orders, showReady)` hiding
      fully-ready dockets
- [x] 1.2 Logic tests: alerts still first, newest-first within equal severity, ready hidden by
      the filter and shown/sorted-last when requested

## 2. Board state + UI

- [x] 2.1 `useKdsBoard.ts`: `showReady` ref (default off) + `readyCount` computed;
      `filteredOrders` applies the visibility filter; toggling resets pagination
- [x] 2.2 `KdsTopBar.vue`: "Listas (N)" toggle pill (ember when active, live count,
      `aria-pressed`)

## 3. Validation

- [x] 3.1 Frontend gates green (`pnpm type-check`, `test:unit`, `lint`, `build`)
- [x] 3.2 Dev check: with open orders on the board, the newest fired shows first (alerts still
      on top); complete one order → it disappears and "Listas (1)" appears; toggle shows it at
      the end
