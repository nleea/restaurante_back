# Tasks: wire-delivery-routes-map

## 1. Backend — settings + route map data

- [x] 1.1 `DeliverySettingModel` (`delivery_settings`: branch_id unique FK, latitude/longitude
      Numeric(10,7) nullable, ring_step_km Numeric(4,2) default 1.0) + entity + ports/repo
- [x] 1.2 `delivery_routes` columns: `color` String(7) nullable, `position` Integer NOT NULL,
      `zones` JSON NOT NULL default `[]`; entities/schemas swap `covered_zones` for `zones`
- [x] 1.3 Migration `0008_delivery_settings_and_route_map_data`: create table, add columns,
      backfill `zones` from `covered_zones` (split commas, trim), backfill `position`
      sequentially per branch by creation order, drop `covered_zones`; downgrade restores it
- [x] 1.4 Endpoints: `GET /delivery/settings?branch_id=` (lazy-create defaults, `delivery.read`)
      and settings update (`delivery.manage`, step clamped 0.5–5.0); route create/update accept
      `zones` (≤20×≤60) and `color`; create assigns next `position`; list ordered by position
- [x] 1.5 Derived driver status in `list_route_drivers`: `inactive` (assignment inactive),
      `on_route` (employee has a run in preparing/in_transit), else `available` — one query,
      exposed on the response schema
- [x] 1.6 Backend tests: lazy settings creation, coords update, step validation, zones
      validation + migration-shaped data, position assignment/ordering, driver status derivation
      (with and without active runs), RBAC on new endpoints

## 2. Frontend — service + store

- [x] 2.1 `services/delivery.api.ts`: `DeliverySettings` type + get/update; `Route` gains
      `zones: string[]`, `color: string | null`, `position`; `RouteDriver` gains `status`;
      service tests
- [x] 2.2 `stores/delivery.ts`: settings state + `loadSettings`/`saveSettings` (debounce lives
      in the view); routes/drivers carry the new fields; write-through preserved; store tests

## 3. Frontend — wire the map view

- [x] 3.1 View model seam: map API routes/drivers into the prototype's view types in one place
      (color fallback by position from the palette when null); `lib/deliveryRoutes.ts` seed
      confined to tests
- [x] 3.2 `DeliveryRoutesView.vue` consumes the store: routes list, create/edit (name, zones,
      color) and deactivate/reactivate via API; assign/remove drivers via existing endpoints
      with friendly duplicate handling; status pills from API status
- [x] 3.3 Ring step: slider drives the map from local state and persists debounced (~500 ms) via
      settings update; reload shows persisted rings
- [x] 3.4 Location onboarding: no coordinates → banner + optional `navigator.geolocation`
      centering suggestion → map click places the pin → confirm persists (`delivery.manage`) →
      rings appear; "Reubicar" in the radius panel re-enters pick mode
- [x] 3.5 Mutation gating: without `delivery.manage`, the screen is read-only (no create/edit/
      assign/slider/pin affordances)

## 4. Routing + retirement

- [x] 4.1 `/delivery` renders the map view inside `AppShell` (requiresAuth, `delivery.read`);
      remove the public `/delivery-routes` route; delete old `DeliveryView.vue` and its
      route-form components; migrate any still-relevant tests
- [x] 4.2 Sidebar unchanged ("Domicilios" → `/delivery`); verify `/dispatch` untouched

## 5. Validation

- [x] 5.1 Backend gates green (pytest, ruff, mypy) and `alembic upgrade head` applied to dev
- [x] 5.2 Frontend gates green (`pnpm type-check`, `test:unit`, `lint`, `build`)
- [x] 5.3 E2E on dev: fresh branch → onboarding places the pin → create a route with zones and
      color → ring renders at band 1 → assign a driver → status pill shows; start a run in
      `/dispatch` → driver reads "En ruta" here; move the slider → reload keeps the new rings;
      old data check: pre-existing routes show their comma-split zones
