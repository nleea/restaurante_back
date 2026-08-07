## Context

`StorefrontService` resolves the branch itself, in two places:

```
manage_storefront.py:86    branch_id = await self._repo.get_primary_branch_id(tenant_id)   # get_menu
manage_storefront.py:101   branch_id = await self._repo.get_primary_branch_id(tenant_id)   # create_order
```

Everything downstream is already branch-correct — `build_menu(tenant, branch)`,
`_resolve_lines(tenant, branch, …)`, `resolve_system_employee(tenant, branch)`,
`open_order(…, branch_id, …)`. The branch is threaded properly; it is just always the same
one. So this change is narrow: replace the resolver, not the plumbing.

`BranchModel` (`shared/tenancy/models.py:52`) has `code: String(32)` with
`UniqueConstraint(tenant_id, code)` and the docstring "The pair (`tenant_id`, `code`) is
unique to allow a human-readable identifier per tenant." Nothing constrains its format
today, so `Sede #1 (Centro)` is currently a legal code and would produce a broken URL.

The tenant is already resolved from the subdomain, so the URL composes as
`<tenant-slug>.<base_domain>/store/<branch-code>` with no ambiguity between the two
identifiers.

We are in development with no production data (see `docs/messaging/ROADMAP.md`), so
tightening the `code` format and changing public endpoint signatures costs nothing now and
would be expensive later.

## Goals / Non-Goals

**Goals:**
- Make the public menu and order intake addressable per branch through `branches.code`.
- Keep single-branch tenants working with no link change.
- Make a wrong branch code loud (404), never silent.

**Non-Goals:**
- Per-branch appearance/theming — appearance stays tenant-level.
- The `store_token` that pre-fills the checkout (belongs to `whatsapp-channel`).
- Letting the customer change branch mid-cart. Changing branch means a new menu, new
  prices and possibly different availability; the cart is not portable and we will not
  pretend it is.
- Any data migration.

## Decisions

**1. The branch is a path segment, not a body field or a query param.**
`/storefront/{branch_code}/menu` and `/storefront/{branch_code}/orders`. A path segment is
what a customer can be handed in a WhatsApp message, is cacheable per branch, and — because
it is not part of `StorefrontOrderCommand` — cannot be tampered with by editing the cart
payload. The menu the customer saw and the branch the order lands on are the same URL.
*Alternative considered:* `?branch=centro`. Rejected — invisible in a pasted link, easy to
drop, and query params get stripped by some WhatsApp previews.

**2. An unknown or inactive code is 404. Never fall back to the primary branch.**
Falling back is the dangerous failure: the customer believes they ordered from Centro, the
ticket prints in Norte, and nobody finds out until the food is late. A 404 is recoverable;
a wrong kitchen is not.
*Alternative considered:* fall back with a warning banner. Rejected — the order is created
before anyone reads a banner.

**3. Keep the code-less endpoints, resolving the primary branch.**
`GET /storefront/menu` and `POST /storefront/orders` stay as they are. This keeps
single-branch tenants (the common case) on a shorter link, keeps the current front working,
and means this change breaks nothing.
*Alternative considered:* make the code mandatory. Rejected — forces every tenant to know
its branch codes for no benefit, and would break the existing storefront in the same commit
that introduces the branch concept.

**4. `branches.code` is validated as a slug at the application boundary, not by a DB CHECK.**
Format: `^[a-z0-9]+(-[a-z0-9]+)*$`, max 32 (the column width already). Validating in the
branch write path keeps the rule in one readable place and gives a proper 422 instead of an
opaque integrity error. The uniqueness that actually matters is already a DB constraint.
*Alternative considered:* a separate `slug` column beside `code`. Rejected — two
human-readable identifiers per branch is one too many, and `code` already carries the
docstring's intent.

**5. Branch resolution lives in the repository, beside `get_primary_branch_id`.**
`get_branch_id_by_code(tenant_id, code) -> uuid | None`, filtered to `is_active`. The
service raises the not-found error; the repository stays a dumb lookup. Same shape as the
resolver it sits next to.

**6. `GET /storefront/branches` returns only active branches.**
An inactive branch must not be selectable, for the same reason its code 404s. The listing
carries `code`, `name`, `address` — enough for a picker, nothing internal.

## Risks / Trade-offs

- **Cart is not portable across branches.** If a customer opens `/store/centro`, fills a
  cart, then opens `/store/norte`, the front must clear the cart rather than carry line
  items that reference another branch's prices. Handled in the front; the backend already
  rejects unknown variants per branch in `_resolve_lines`.
- **Codes become public.** `branches.code` moves from an internal label to a customer-facing
  URL. Renaming one breaks every link already sent over WhatsApp. Worth saying out loud in
  the branch admin UI later; not solved here.
- **Two live shapes for the same endpoint** (with and without code) is mild duplication. The
  code-less form delegates to the coded one after resolving the primary branch, so there is
  one implementation and two entry points.

## Migration Plan

No data migration. Dev seeds are updated so every seeded branch has a slug-safe `code`. Any
existing dev row with a non-conforming code is re-seeded, not patched.

## Open Questions

- Should the branch picker remember the last-used branch in the guest cookie? Convenient,
  but risks a returning customer silently ordering from a branch they no longer meant. Left
  out of this change; revisit if the picker proves annoying.
