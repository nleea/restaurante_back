# Tasks: delivery-address-picker

> Rebased 2026-07-03 onto the dispatch board (`dispatch-board-redesign`): targets are
> `views/DispatchView.vue` (the "Nuevo domicilio" modal and the right detail pane).

## 1. Foundations

- [x] 1.1 `lib/geo.ts`: `parseSharedLocation(text)` — decimal `lat,lng` pairs and Google Maps
      URL shapes (`@lat,lng`, `?q=lat,lng`, `?q=loc:lat,lng`, `!3d…!4d…`), range-validated,
      `null` on anything else — with unit tests (including short-link → null)
- [x] 1.2 `services/delivery.api.ts`: `updateDelivery` patch type gains
      `latitude`/`longitude` (backend already accepts them); service test

## 2. Picker component

- [x] 2.1 `components/dispatch/LocationPickerMap.vue` (folder recreated): reusable mini Leaflet
      map (reuses the CDN loader), `modelValue` point + `center` props, tap-to-set with
      candidate marker, `invalidateSize` after mount/dialog-open (Leaflet-in-modal pitfall)

## 3. Board integration (`views/DispatchView.vue`)

- [x] 3.1 "Nuevo domicilio" modal: optional "Ubicación en el mapa" section — paste field
      (parse → pan + set candidate, friendly copy on unparseable) + mini-map centered on the
      branch pin (delivery settings); send coordinates only when set
- [x] 3.2 Delivery detail pane: show whether it carries a location; "Agregar/corregir
      ubicación" opens the picker in a dialog and PATCHes coordinates (write-through refetch)
- [x] 3.3 Delivery cards hint located vs sin-ubicación (subtle icon, no color noise)

## 4. Validation

- [x] 4.1 Frontend gates green (`pnpm type-check`, `test:unit`, `lint`, `build`)
- [x] 4.2 E2E on dev: create a delivery tapping the mini-map → coordinates persisted and dot on
      the coverage map (`/delivery`); paste a Maps link → same; add a location to an existing
      "sin ubicación" delivery from the detail pane → the map's counter drops
