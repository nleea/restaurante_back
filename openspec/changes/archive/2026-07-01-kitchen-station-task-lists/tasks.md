# Tasks: kitchen-station-task-lists

## 1. Backend — task lists on mappings and tickets

- [x] 1.1 Migration `0007_station_task_lists`: `tasks` JSON NOT NULL DEFAULT '[]' on
      `product_stations` and `order_item_stations`; ORM models + domain entities gain
      `tasks: list[str]`
- [x] 1.2 Routing copies the mapping's tasks onto each created ticket (frozen at fire time,
      same semantics as `role`); `list_stations_for_product` returns tasks alongside role
- [x] 1.3 `PATCH /kitchen/product-stations/{mapping_id}` (partial `{role?, tasks?}`,
      `kitchen.update`, tenant-guarded); attach accepts optional `tasks`; schema validation:
      ≤10 tasks, each 1–60 chars, trimmed, empties dropped
- [x] 1.4 `TicketResponse` and `ProductStationResponse` expose `tasks`
- [x] 1.5 Backend tests: attach with tasks, patch role/tasks in place, oversized list rejected
      (422), routing copies tasks, config edit doesn't rewrite fired tickets, empty default

## 2. Frontend — read-only task lines on the board

- [x] 2.1 `services/kitchen.api.ts`: `tasks: string[]` on `Ticket` and `ProductStation`;
      `updateProductStation(mappingId, patch)` for the new PATCH
- [x] 2.2 `lib/kds/types.ts` + `adapter.ts`: `KdsComponent.tasks` copied from the ticket;
      adapter tests for tasks passthrough and empty default
- [x] 2.3 `KdsItemRow.vue`: render each component's tasks as compact mono sub-lines
      (`· Carne de hamburguesa`), dimmed/collapsed when the component is done
- [x] 2.4 `KdsMyStation.vue`: station rows show the component's task list so the cook reads the
      dish's itemized work for their station
- [x] 2.5 Seed (`lib/kds/seed.ts`) and mock meta updated so dev/tests exercise components with
      and without tasks

## 3. Frontend — setup editor

- [x] 3.1 Kitchen store: `updateMapping(productId, mappingId, patch)` write-through action
      (+ tests)
- [x] 3.2 `KitchenSetup.vue`: mapping rows show role + task chips; inline editor to set role and
      add/remove tasks, saved via PATCH; copy notes that already-fired tickets keep their tasks

## 4. Validation

- [ ] 4.1 Backend gates green (pytest, ruff, mypy) and `alembic upgrade head` applied to dev
- [ ] 4.2 Frontend gates green (`pnpm type-check`, `test:unit`, `lint`, `build`)
- [ ] 4.3 E2E on dev: configure Parrilla with ["Carne de hamburguesa", "Tocineta ahumada"] for a
      demo product, route an order → the docket component lists both tasks and my-station shows
      them; edit the config → old ticket unchanged, newly routed order carries the new list
