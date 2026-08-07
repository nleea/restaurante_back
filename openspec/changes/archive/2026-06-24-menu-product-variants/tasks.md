## 1. Backend — product variants API

- [x] 1.1 Add repository methods over `ProductVariantModel`/`ProductVariantOptionModel`: `create_product_variant` (with optional option ids), `list_product_variants(product_id)`, `get_product_variant`, `update_product_variant`, `delete_product_variant`, and a helper that sums composed options' `extra_price` per variant.
- [x] 1.2 Add `MenuService` use cases mirroring the variant-group/option ones: create (validate supplied option ids belong to the product's variant groups), list (returning each variant + derived `extra_price`), update (name/is_active), delete.
- [x] 1.3 Add request/response schemas: `ProductVariantResponse` (`id`, `product_id`, `name`, `is_active`, `extra_price`), `CreateProductVariantRequest` (`name?`, `variant_option_ids?`), `UpdateProductVariantRequest` (`name?`, `is_active?`).
- [x] 1.4 Add routes: `GET`/`POST /menu/products/{product_id}/variants` (read/manage), `PATCH`/`DELETE /menu/variants/{variant_id}` (manage).
- [x] 1.5 Integration tests: list with derived `extra_price`; create plain (`extra_price = 0`); create composed (summed `extra_price`); reject a foreign option id; rename + deactivate; delete; RBAC gates (`menu.read`/`menu.manage`).
- [x] 1.6 Run `ruff`, `mypy`, and `pytest` green.

## 2. Frontend — menu service & store

- [x] 2.1 Add to `services/menu.api.ts`: `listVariants(productId)`, `createVariant(productId, { name?, variant_option_ids? })`, `updateVariant(variantId, patch)`, `deleteVariant(variantId)`, with a `ProductVariant` type (incl. `extra_price`).
- [x] 2.2 Add `stores/menu.ts` actions: hold variants per product (or fetch on demand), `addVariant`, `removeVariant`, `renameVariant` with write-through refetch.
- [x] 2.3 Unit tests: list/create/delete forwarding, and that `extra_price` flows through untouched.

## 3. Frontend — variants in the product detail

- [x] 3.1 Add a "Variantes vendibles" section to `components/menu/ProductDetail.vue`: list variants with name + extra price; an inactive badge for inactive ones.
- [x] 3.2 Add-variant control (gated by `menu.manage`): a name field, and — when the product has variant options available — an optional multi-select to compose them; submit via the store.
- [x] 3.3 Delete-variant control (gated by `menu.manage`); hide add/delete entirely without `menu.manage`.
- [x] 3.4 Show the orderable price hint (active-branch price + `extra_price`) and style with the "El Pase" design system (PrimeIcons `.pi` responsive-class caveat).

## 4. Validation

- [x] 4.1 Frontend: type-check, lint (oxlint + eslint), unit tests, and production build all green.
- [x] 4.2 Verified at the test level: backend integration tests cover list/create-plain/create-composed/foreign-option/update/delete/RBAC; frontend unit tests cover load/add/remove/rename with extra_price passthrough; type-check/lint/build green. Live browser walkthrough not run in this pass.
