## Why

The Orders module (comandas) cannot be built on the frontend yet: an order item references a `product_variant_id` (a sellable SKU in `product_variants`), but **the menu module exposes no API for product variants** — the table and domain entities exist, yet there is no repository/service/endpoint, so the order tests insert `ProductVariantModel` rows straight into the DB. Worse, a product created from the menu frontend has **zero** sellable variants, so it can never be ordered. This change adds the missing product-variants layer (backend + menu UI) so every product becomes orderable and the upcoming comandas screen has variants to pick and price.

## What Changes

- **Backend — product variants API** (menu): add a functional layer over the existing `ProductVariantModel`:
  - `GET /menu/products/{product_id}/variants` — list a product's sellable variants. Each carries `id`, `product_id`, `name`, `is_active`, and a derived `extra_price` (the sum of its composed variant options' `extra_price`, `0` for a plain variant).
  - `POST /menu/products/{product_id}/variants` — create a variant: optional `name`, optional `variant_option_ids` to compose (validated to belong to the product's variant groups).
  - `PATCH /menu/variants/{variant_id}` — rename / activate-deactivate.
  - `DELETE /menu/variants/{variant_id}`.
- **Price derivation contract**: a variant's orderable unit price = the product's active-branch price (existing `/menu/products/{id}/prices`) **plus** the variant's `extra_price`. The API exposes `extra_price` so clients (orders) can compute `unit_price` without re-reading options.
- **Frontend — manage variants in the menu** (`frontend-menu`): in the product detail, a "Variantes vendibles" section to list variants (name + extra price), add a variant (name; and, when the product has variant options, optionally compose them), and delete one. Plain named variants (e.g. "Estándar") are the common path and make a product orderable immediately.
- **Out of scope (deferred)**: managing variant *groups/options* themselves in the frontend (composed/priced variants rely on options that exist; this change manages the sellable variants, not the option catalog), and the comandas screen itself (the next change, which consumes this).

## Capabilities

### New Capabilities
- `menu-product-variants`: backend API to list, create, update, and delete a product's sellable variants (SKUs), exposing a derived `extra_price` so order items can be priced.

### Modified Capabilities
- `frontend-menu`: gains a requirement to manage a product's sellable variants from the product detail.

## Impact

- **Backend**: new repository methods, service use cases, request/response schemas, and `/menu/.../variants` routes over the existing `ProductVariantModel` / `ProductVariantOptionModel` (domain entities already exist). New integration tests. No migration (tables exist).
- **Frontend**: `services/menu.api.ts` (+ variants), `stores/menu.ts` (variant actions), and `components/menu/ProductDetail.vue` (new section). Unit tests.
- **Unblocks**: the comandas frontend — order items can now discover a `product_variant_id` and compute its `unit_price`. Establishes that every product can carry at least one sellable variant.
