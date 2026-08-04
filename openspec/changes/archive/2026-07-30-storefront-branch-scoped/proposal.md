## Why

The public storefront is hardcoded to one branch. `StorefrontService.get_menu` and
`create_order` both resolve the branch with `get_primary_branch_id(tenant_id)`
(`manage_storefront.py:86,101`), so **every web order lands on the primary branch** no
matter which branch the customer meant. A tenant with three branches has one usable
storefront.

This blocks the WhatsApp program (see `docs/messaging/ROADMAP.md`): the plan is one
WhatsApp session per branch, and the greeting answers an incoming message with a link to
*that branch's* menu. The branch has to be addressable in the URL before anything can send
that link.

`branches.code` already exists as `UNIQUE(tenant_id, code)` and its docstring states it is
there "to allow a human-readable identifier per tenant" — it is the slug. Nothing new needs
to be modelled; it only needs to be URL-safe and actually used.

## What Changes

- **`GET /storefront/menu` and `POST /storefront/orders` take a branch code.** The tenant
  still comes from the subdomain; the branch comes from the path
  (`/storefront/{branch_code}/menu`, `/storefront/{branch_code}/orders`). The menu, prices,
  hours and order all resolve against that branch.
- **`branches.code` is constrained to URL-safe** (lowercase letters, digits, hyphens),
  validated on write. Existing dev rows are re-seeded, not migrated.
- **A tenant-level fallback stays.** `GET /storefront/menu` with no branch code keeps
  resolving the primary branch, so a tenant with one branch needs no link change and the
  existing customer flow does not break.
- **An unknown or inactive branch code is a 404**, not a silent fall back to the primary
  branch — falling back would send the customer's order to the wrong kitchen.
- **The front's `/store` route becomes `/store/:branchCode?`**, and the checkout posts to
  the branch-scoped endpoint. When no code is given it behaves exactly as today.
- **`GET /storefront/branches`** lists the tenant's active branches (code, name, address)
  so the storefront can offer a picker when the customer arrives without a code.

Out of scope (later changes in the roadmap): the WhatsApp channel itself, the greeting that
sends the link, the `store_token` that pre-fills the checkout, and any per-branch appearance
(appearance stays tenant-level).

## Capabilities

### Modified Capabilities
- `storefront-public-api`: the public menu and order intake are branch-addressable via
  `branches.code`; unknown/inactive codes 404; a branch listing endpoint is added; the
  no-code form keeps resolving the primary branch.
- `frontend-storefront`: the storefront route carries an optional branch code, renders that
  branch's menu and hours, and submits the order to that branch; a picker appears when no
  code is supplied and the tenant has more than one active branch.

## Impact

- **Backend**: `StorefrontService.get_menu` / `create_order` take `branch_id`; a new
  resolver maps `(tenant, code) → branch` and raises a not-found error for unknown or
  inactive codes; router paths gain the branch segment; `branches.code` gains a format
  validator. No migration of data — dev only, per the roadmap.
- **`StorefrontOrderCommand`** gains nothing: the branch is a resolver argument, not cart
  data, so the customer cannot pick a branch by editing the payload.
- **Frontend**: `/store/:branchCode?`, storefront store/view read the code from the route,
  new branch picker for the no-code case.
- **Not breaking for existing callers**: the code-less endpoints keep working and keep
  resolving the primary branch.
- **Unblocks**: `whatsapp-channel` and, after it, the greeting that sends
  `/store/<branch-code>`.
