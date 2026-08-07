# Tasks — dispatch-board-redesign

## 1. Backend: timestamps + notes (additive)

- [x] 1.1 Add `TimestampMixin` and `notes: Mapped[str | None] (String(500))` to `OrderDeliveryModel`; generate the Alembic migration (server-default backfill for `created_at`/`updated_at`)
- [x] 1.2 Expose `created_at` on the delivery response schema and `created_at` on the run response schema; add `notes` to delivery response and to the PATCH input (≤ 500 chars validation)
- [x] 1.3 Extend `update_delivery` use case to persist `notes`; keep the `delivery.manage` gate
- [x] 1.4 Backend tests: created_at present on delivery/run reads, notes round-trip via PATCH, overlong notes rejected; `ruff` + `mypy` pass

## 2. Frontend service + store

- [x] 2.1 Add `created_at`/`notes` to `Delivery` and `created_at` to `Run` in `services/delivery.api.ts`; extend `updateDelivery` patch type with `notes`
- [x] 2.2 Extend `stores/dispatch.ts` with the board helpers (run progress/stops via `route_position` order, `updateDeliveryNotes` write-through action); unit tests for new store surface

## 3. Wire the board (in place at /dispatch/design)

- [x] 3.1 Replace mock state in `DispatchDesignView.vue` with the `dispatch`/`delivery`/`staff`/`orders` stores (load pattern and label helpers from the current `DispatchPanel`); map statuses `pending→Sin asignar`, `not_delivered→No entregado`; delete elapsed/heat mock clock in favor of `created_at`-based real times
- [x] 3.2 Stats + filters on real data (status/route/driver/address search; "hoy" from `created_at`)
- [x] 3.3 Delivery detail: timeline from real timestamps (asignado without time), notes editor via `updateDeliveryNotes`, "No entregado" only for `in_transit` (markDelivered(false)), permission gates (`delivery.manage`/`delivery.assign`) as in the current screen
- [x] 3.4 Replace direct driver assignment with the assign-to-run picker (list `preparing` runs + shortcut to create a run pre-seeded with the delivery); reuse it for moving `assigned` deliveries
- [x] 3.5 "Nuevo domicilio" modal: open-order Select (required), address, neighborhood, notes; friendly duplicate-order conflict message; drop route/driver/phone fields
- [x] 3.6 "Nuevo despacho" two-step modal on real data: drivers from routes (`listDrivers`), busy/inactive not selectable, create run then `assignDelivery` each selected delivery; "Agregar domicilio" in run detail gated to `preparing`
- [x] 3.7 Run lifecycle on store actions (`departRun`/`finishRun`); keep the client-side "all stops resolved" gate on Finalizar; friendly 409 messages throughout

## 4. Swap and cleanup

- [x] 4.1 Verify feature parity end-to-end against the seeded backend (create delivery → run → assign → depart → deliver/no-deliver → finish; filters; mobile drill-down)
- [x] 4.2 Point `/dispatch` at the board; delete `/dispatch/design` route, `DispatchView.vue` (old), `components/dispatch/*`, and `lib/dispatchDesignMock.ts`; rename the view to `DispatchView.vue`
- [x] 4.3 Frontend quality gates: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`
- [x] 4.4 Note for `delivery-address-picker`: rebase its form tasks onto the new "Nuevo domicilio" modal (update that change's tasks.md pointer)
