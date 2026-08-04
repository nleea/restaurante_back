## 1. Backend · migration

- [x] 1.1 Add migration `0016_menu_appearance`: create `menu_appearance` (`id`, `tenant_id` unique,
  `config jsonb not null`, timestamps) and add `ingredients.is_customer_removable boolean not null
  default true`.
- [x] 1.2 Verify upgrade/downgrade run cleanly against a scratch DB.

## 2. Backend · ingredient flag (recipes module)

- [x] 2.1 Add `is_customer_removable: Mapped[bool]` (default True) to `IngredientModel`.
- [x] 2.2 Surface it in ingredient domain entity, create/update use cases, and repository mapping.
- [x] 2.3 Add it to ingredient request/response Pydantic schemas (create/update/read), default true.
- [x] 2.4 Update/extend recipes ingredient tests to cover the flag (create default true, set false,
  round-trips on list/retrieve).

## 3. Backend · appearance persistence (menu module)

- [x] 3.1 Add `MenuAppearanceModel` (tenant-scoped, unique tenant, `config` JSONB) + repository
  (get-by-tenant, upsert).
- [x] 3.2 Add a Pydantic `MenuAppearanceConfig` schema mirroring the frontend shape
  (theme/brand/blocks/dishCard/dishDetail/blockContent), and a `default_appearance_config()` builder
  matching the frontend defaults.
- [x] 3.3 Add use cases: `get_appearance` (saved or default) and `save_appearance` (upsert +
  validate).
- [x] 3.4 Add router endpoints `GET /menu/appearance` (`menu.read`) and `PUT /menu/appearance`
  (`menu.manage`); PUT returns the saved config.
- [x] 3.5 Tests: default on first read, upsert creates then overwrites (one row), tenant isolation,
  RBAC 403s, malformed payload 422.

## 4. Frontend · appearance API + store

- [x] 4.1 Add `services/menuAppearance.api.ts`: `getAppearance()` and `putAppearance(config)` typed
  to `MenuAppearanceConfig`.
- [x] 4.2 Rewrite store `load()` to be async: seed defaults synchronously, then GET and reconcile
  published+draft; on failure keep defaults (editor still opens).
- [x] 4.3 Rewrite `publish()` to `await putAppearance(draft)` then set published from the response;
  keep `discard()`/`isDirty`.
- [x] 4.4 Update `MenuAppearanceView` mount to await the async `load()` (it already loads menu data
  in parallel).

## 5. Frontend · ingredient flag

- [x] 5.1 Add `is_customer_removable` to the `Ingredient` type in `services/recipes.api.ts` and to
  `CreateIngredientInput`/update paths.
- [x] 5.2 Filter removables by the flag: `removableIngredientsFor` (or `DishDetailPreview`) keeps
  only ingredients whose `is_customer_removable` is true.
- [x] 5.3 Add a "Quitable por el cliente" toggle to the insumo editor (inventory/insumos board),
  wired write-through like the other ingredient fields.
- [x] 5.4 Update the `removableIngredientsFor` unit test for the flag filtering.

## 6. Verify

- [x] 6.1 Backend: `poetry run pytest` for menu + recipes modules green; `GET`/`PUT /menu/appearance`
  and the ingredient flag behave per spec.
- [x] 6.2 Frontend: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build` clean.
- [ ] 6.3 Manual pass at `demo.localhost`: edit appearance → publish → reload → config persists;
  mark an insumo non-removable → it disappears from the dish-detail "quitar" list.
