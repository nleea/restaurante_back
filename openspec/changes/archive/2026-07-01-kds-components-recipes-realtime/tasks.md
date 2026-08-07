# Tasks: kds-components-recipes-realtime

## 1. Backend — ticket uniqueness hardening

- [x] 1.1 Alembic migration: dedupe existing `order_item_stations` rows (keep the most advanced,
      oldest ticket per pair) and add a unique constraint on
      `(order_item_id, kitchen_station_id)`
- [x] 1.2 `create_ticket`/`route_order` treat the integrity error as "already routed" (keep the
      `ticket_exists` fast path) so concurrent routes converge without failing
- [x] 1.3 Backend tests: double route creates no duplicates; integrity-error path returns
      cleanly

## 2. Backend — recipe details and card

- [x] 2.1 `recipes` module: `RecipeDetail` entity + model (`product_variant_id` unique, `steps`
      JSON list, `allergens` JSON list, `photo_label` nullable) + Alembic migration
- [x] 2.2 Repository + use cases: upsert details, get details, and the aggregated recipe card
      (BOM lines joined with ingredient and unit names + details) in one query path
- [x] 2.3 Router + schemas: `PUT/GET /recipes/variants/{variant_id}/details` and
      `GET /recipes/variants/{variant_id}/card`; allergen keys validated against
      `gluten|dairy|nuts|shellfish|vegan`; permissions follow the module's existing codes
- [x] 2.4 Backend tests: upsert/replace, unknown allergen rejected, card aggregation, BOM-only
      and details-only cards, not-found cases, tenant isolation
- [x] 2.5 Document the new endpoints under `docs/recipes/`

## 3. Backend — kitchen events + SSE

- [x] 3.1 Kitchen event publisher port + Redis pub/sub implementation (channel
      `kds:{tenant_id}:{branch_id}`, reuses `redis_url`); best-effort publish that logs and
      never raises into the mutation path; wired at the composition root
- [x] 3.2 Emit `ticket_created` (route_order) and `ticket_advanced` (advance_ticket) events with
      branch, station, ticket id and status
- [x] 3.3 `GET /kitchen/events?branch_id=` SSE endpoint (`kitchen.read`): subscribes to the
      tenant/branch channel, streams `data:` events, heartbeat comment every ~15 s, unsubscribes
      on client disconnect; serves heartbeats even when Redis is down
- [x] 3.4 Backend tests: events published on route/advance; publish failure doesn't break the
      mutation; stream endpoint rejects without permission

## 4. Frontend — dish components from ticket grouping

- [x] 4.1 `lib/kds/adapter.ts`: group tickets by `order_item_id` → one `KdsItem` with one
      component per ticket; component name = `role` ?? station label; item qty/label from the
      item index; solo unresolvable tickets keep their own docket entry
- [x] 4.2 Adapter tests: multi-station item renders N components, role fallback, dish done only
      when all components done, cross-station alert fires (done component + pending sibling)

## 5. Frontend — recipe drawer on real data

- [x] 5.1 Expose `product_variant_id` through the kitchen store's item index and onto `KdsItem`
      (optional `variantId`) so the drawer can resolve the dish's recipe
- [x] 5.2 `services/recipes.api.ts`: typed `getRecipeCard(variantId)` against
      `/recipes/variants/{id}/card`
- [x] 5.3 `useKdsBoard.ts`: turn `RECIPES_ENABLED` on; `openRecipe` loads the card async with
      `loading | card | none` state; `KdsRecipeDrawer.vue` renders backend card data with a
      loading state and a quiet "sin receta" state (no mock content in production)
- [x] 5.4 Unit tests: recipes API service, drawer open states (loading, card, none)

## 6. Frontend — live board via SSE

- [x] 6.1 `lib/sse.ts`: fetch-stream SSE client (Bearer header from token storage, parses
      `data:` lines, reconnect with backoff, reports connected/error state)
- [x] 6.2 Kitchen store: `startEvents(branchId)` — on kitchen events, debounce ~300 ms and
      refetch (station-targeted for `ticket_advanced`, full board for `ticket_created`); while
      the stream is connected relax polling to ~60 s; on stream error restore ~10 s polling and
      retry the stream
- [x] 6.3 Wire lifecycle in the kitchen screen: start events with polling on mount/branch
      change, stop both on unmount
- [x] 6.4 Tests: SSE client parsing/reconnect with a mocked fetch stream; store event→refetch
      debounce and cadence switching

## 7. Validation

- [x] 7.1 Backend gates green: pytest (module tests) and migrations apply cleanly
      (`alembic upgrade head`)
- [x] 7.2 Frontend gates green: `pnpm type-check`, `pnpm test:unit`, `pnpm lint`, `pnpm build`
- [x] 7.3 E2E against dev backend: map a demo product to two stations with roles and route an
      order → docket shows one dish with two role-named components; author a recipe card and
      open the drawer from the board; with the board open, advance a ticket from another client
      and see it update via SSE within ~2 s; stop Redis and confirm the board degrades to
      polling without errors
