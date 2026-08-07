## 1. Backend: orders → kitchen auto-route hook

- [x] 1.1 In `orders/domain/ports.py`: add an outbound port `KitchenRouting` (Protocol) with `async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None: ...` — so the orders application depends on an interface, not the kitchen module
- [x] 1.2 In `orders/application/use_cases/manage_orders.py`: give `OrderService` an optional `kitchen_routing: KitchenRouting | None = None` constructor dependency; in `add_item`, after the item is created (and totals recomputed), call `route_order(tenant_id, order_id)` best-effort (guarded so a failure does not block the add); no-op when the dependency is absent
- [x] 1.3 In `orders/infrastructure/api/deps.py`: build an adapter implementing `KitchenRouting` that delegates to the kitchen routing service (`KitchenService.route_order`) over the **same request `AsyncSession`** as the order service, and inject it into `OrderService`
- [x] 1.4 Confirm the dependency direction stays one-way (orders application imports no kitchen module code; only `deps.py` at the composition root imports the kitchen service) and `import restaurante.main` has no cycle

## 2. Backend tests

- [x] 2.1 Extend `tests/modules/orders/...` (or kitchen tests): create a station + product→station mapping → open an order → add an item whose product is mapped → assert a kitchen ticket for that item exists at the station (status `pending`) via `GET /kitchen/stations/{id}/tickets`
- [x] 2.2 Add an item whose product has **no** mapping → assert the item is added and no ticket is created
- [x] 2.3 Assert idempotency / no duplicates: adding a second item routes only the new item (existing tickets unchanged); the manual route endpoint still works and creates nothing new for already-ticketed items

## 3. Backend verification

- [x] 3.1 `poetry run ruff check .` and `poetry run mypy src` clean for the changed modules
- [x] 3.2 `poetry run pytest tests/modules/orders tests/modules/kitchen` green (manual routing + KDS tests unaffected)

## 4. End-to-end verification

- [ ] 4.1 Manual smoke against the running backend: configure a station + map a product → open an order → add a mapped item → the ticket appears on the Cocina board **without** clicking "Enviar a cocina"; add an unmapped item → no ticket; add another mapped item → its ticket appears, earlier tickets unchanged; verify a tenant with no stations sees no tickets and item-add still works
