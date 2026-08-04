## Context

Order items reference `product_variants.id` and carry a client-supplied `unit_price`. The menu module has `ProductVariantModel` (a sellable SKU: `product_id`, `name?`, `is_active`) and `ProductVariantOptionModel` (a bridge variant↔`variant_options`), plus the domain entities `ProductVariant`/`ProductVariantOption` — but **no repository methods, service use cases, or endpoints** for them. Variant *groups* and *options* do have an API (`/menu/variant-groups`, `/menu/variant-groups/{id}/options`, each option carrying `extra_price`). Product prices are per-product per-branch (`/menu/products/{id}/prices`). The menu frontend manages categories, products, prices, and addons — it surfaces no variants at all.

Net: a product created today has zero sellable variants and is therefore un-orderable, and a client has no way to list or create one. This change adds the variants layer so comandas can be built next.

## Goals / Non-Goals

**Goals:**
- A backend CRUD surface for a product's sellable variants, exposing a derived `extra_price`.
- A price-derivation contract: variant unit price = product active-branch price + variant `extra_price`.
- A menu-frontend section to manage a product's variants, so every product gets at least one orderable unit.

**Non-Goals:**
- Managing variant *groups/options* in the frontend (the option catalog) — a later change; composed/priced variants depend on options already existing.
- The comandas screen (the next change, which consumes this).
- Changing how product prices work, or moving price onto variants.
- Bulk variant operations or per-branch variant pricing.

## Decisions

### 1. Variants live in the menu module, mirroring variant-groups/options
Add repository methods + `MenuService` use cases + schemas + routes alongside the existing variant-group/option code, reusing the `ProductVariant`/`ProductVariantOption` domain entities. Paths: `GET/POST /menu/products/{product_id}/variants`, `PATCH/DELETE /menu/variants/{variant_id}`. **Alternative considered:** a new module — rejected; variants are intrinsically menu data and the patterns already exist there.

### 2. `extra_price` is derived, never stored on the variant
`ProductVariantModel` has no price column by design — a variant's price delta comes from its composed `variant_options.extra_price`. The list/response computes `extra_price = sum(option.extra_price)` (0 when no options). This keeps a single source of truth (the options) and lets a plain variant represent "the product at its base price." **Alternative considered:** add an `extra_price` column to the variant — rejected; it would duplicate/contradict the options and require a migration.

### 3. Price contract stays client-computed for orders
Orders already pass `unit_price` per item. This change does not introduce a server-side "variant price" endpoint; it exposes `extra_price` so the orders frontend computes `unit_price = branchPrice(product) + variant.extra_price`. Branch price comes from the existing prices endpoint and the active-branch context. **Alternative considered:** a resolved per-branch variant price endpoint — deferred; not needed to unblock comandas and would couple variants to branch pricing.

### 4. Plain variants are the common path
For pilot products without size/option variations, the menu UI adds a plain named variant (e.g. "Estándar", no options, `extra_price = 0`). Composed variants (picking existing options) are supported when the product has variant options, but are optional. This makes every product orderable with one click and avoids forcing the (unmanaged) option catalog into this change.

### 5. Option validation on create
When `variant_option_ids` are supplied, the service validates each belongs to one of the product's variant groups (reusing the existing group/option reads), rejecting foreign options. Plain variants skip this entirely.

## Risks / Trade-offs

- **Composing options requires options to exist** → the frontend offers composition only when the product has variant options; otherwise it offers plain variants. No dead-end UI.
- **A product with multiple plain variants is ambiguous for orders** → acceptable; the orders screen lists all active variants and the operator picks. Naming ("Estándar") keeps it clear.
- **Derived `extra_price` adds a join per list** → variant lists are tiny (a handful per product); negligible.
- **Deleting a variant referenced by a historical order item** → `product_variants` delete is `RESTRICT`-guarded by FKs at the order layer; a delete that violates it surfaces as a conflict the UI reports (consistent with other menu deletes).

## Migration Plan

1. Backend: repository (create/list/get/update/delete + option attach + extra_price sum), `MenuService` use cases, schemas, routes. Integration tests: list with derived extra_price, create plain, create composed, reject foreign option, patch/delete, RBAC gates. Run `ruff`/`mypy`/`pytest`.
2. Frontend: `menu.api.ts` variants functions, `menu.ts` store actions, `ProductDetail.vue` "Variantes vendibles" section. Unit tests.
3. Validate: type-check, lint, unit, build.

Rollback: endpoints and UI section are additive; removing the section and routes reverts cleanly.

## Open Questions

- Should creating a product auto-create a default "Estándar" variant so it is orderable without an extra step? Default: no (explicit add in this change); revisit if the comandas flow feels heavy.
- Should the variants list include inactive variants by default? Default: yes for management (with an inactive badge); the orders screen will filter to active.
