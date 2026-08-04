## Context

The backend `/delivery` module is complete but unconsumed. This change builds only its **route +
driver configuration** slice; the per-order deliveries, dispatch runs, and the lifecycle board are a
deliberate follow-up (`frontend-delivery-dispatch`, which uses the separate `delivery.assign`
permission). The route contract:

- **Routes** (branch-scoped — `branch_id` in body and as the list filter): `POST /delivery/routes`
  (`{ branch_id, name, covered_zones? }`), `GET /delivery/routes?branch_id=`,
  `PATCH /delivery/routes/{id}` (`{ name?, covered_zones?, is_active? }`). There is **no** GET-by-id
  and **no** DELETE — deactivation is `PATCH { is_active: false }`. Perm `delivery.read` (read) /
  `delivery.manage` (write).
- **Route drivers** (tenant-scoped, unique `(route, employee)`): `POST /delivery/routes/{id}/drivers`
  (`{ employee_id }`), `GET /delivery/routes/{id}/drivers`,
  `DELETE /delivery/routes/{id}/drivers/{employeeId}`.
- `Route = { id, branch_id, name, covered_zones, is_active }`; `covered_zones` is a **plain string**
  (free text, ≤500 chars), not a list. `RouteDriver = { id, delivery_route_id, employee_id,
  is_active }`.

Two facts drive the design: (1) **routes are branch-scoped**, so the screen uses the active-branch
context (the list filters by `branch_id`, and create sends it) — like inventory, unlike the
tenant-scoped suppliers; and (2) drivers carry only `employee_id`, so names are resolved from the
staff directory the other screens already use, and the assign picker is the active branch's
employees. There is no money on this screen. Conventions follow the existing screens (Vue 3
`<script setup>`, Pinia options stores, PrimeVue + Tailwind, the shared `@/lib/http` axios instance,
active-branch scope, mobile-first master–detail as in Inventory/Purchasing).

## Goals / Non-Goals

**Goals:**
- A self-sufficient route-configuration screen: create/edit/deactivate branch routes and manage each
  route's drivers (assign/remove), scoped to the active branch.
- Reuse the staff employee directory + picker for drivers; mirror the established store discipline
  (write-through, `can()` gating) and master–detail UX.

**Non-Goals:**
- Per-order delivery records, dispatch runs, and the assign/depart/deliver/finish lifecycle
  (follow-up `frontend-delivery-dispatch`).
- Cash-on-delivery capture (orders→cash), auto-assignment/optimization, live GPS, and order-status
  reflection — all out of the backend capability's scope.

## Decisions

**1. One `DeliveryView`, master–detail, like Inventory/Purchasing.** A route list (master) with an
active filter, and a per-route detail holding the name/zones edit form and the driver list. On
`< lg` the list drills into a full-screen detail; on `>= lg` both panes show. Rejected: separate
routes/drivers screens — drivers are owned by a route and belong in its detail.

**2. Branch-scoped via the active-branch context.** The store loads routes with `branch_id =
activeBranchId`, create sends it, and re-scoping on branch change clears the selection and reloads —
exactly the inventory pattern. Route drivers are tenant-scoped server-side but always reached
through a (branch) route, so the screen treats them as belonging to the selected route.

**3. Deactivate is a PATCH; full edit is supported.** Unlike some modules, `PATCH /routes/{id}`
accepts `name`/`covered_zones`/`is_active`, so the detail offers a real edit form (name + zones) plus
a distinct deactivate/reactivate action, all routed through `updateRoute`. No DELETE exists, so
deactivation is the removal affordance.

**4. `covered_zones` is free text.** It renders and edits as a single text field (a textarea for
the longer ≤500-char content); no chip/list parsing — the backend stores a plain string. A short
hint suggests comma-separated neighbourhoods, but nothing is enforced.

**5. Drivers reuse the staff picker; names resolved from staff.** The assign dialog lists the active
branch's employees (load on demand via the staff store), and each driver row resolves its
`employee_id` to a name via `staff.employeeName`, degrading to a short id ref when unresolved. The
picker excludes employees already assigned to the route to avoid the duplicate-assign conflict up
front; a surfaced 409 still shows a friendly message.

**6. Store shape parallels the inventory/purchasing stores.** State: `routes: Route[]`,
`selectedRouteId`, `drivers: RouteDriver[]` (the selected route's drivers). Getters:
`selectedRoute`, `activeRoutes`. Actions (each write-through): `loadRoutes(branchId)`,
`selectRoute(id)` (loads its drivers), `createRoute`, `updateRoute`, `deactivateRoute`,
`assignDriver`, `removeDriver`.

**7. Permission model mirrors existing screens.** Route guard `meta.permission: 'delivery.read'`;
within the view, `auth.can('delivery.manage')` gates every mutate control. Read-only users see
routes and drivers without action affordances. The backend enforces the same permissions regardless.

## Risks / Trade-offs

- **Driver name resolution is best-effort** → an employee not in the loaded staff directory shows a
  short id ref. → Mitigation: load staff for the active branch when the screen opens; degrade
  clearly.
- **Duplicate driver assignment returns a conflict** → Mitigation: the assign picker excludes
  already-assigned employees, and a surfaced 409 shows "ese conductor ya está asignado".
- **No GET-by-id for a route** → the detail renders from the loaded list row; after an edit the
  write-through `loadRoutes` refresh keeps it current. Acceptable — the per-branch route list is
  small.
- **Cross-branch drivers** → route-drivers are tenant-scoped, so an employee from another branch
  could be assigned; the picker offers the active branch's employees by default but does not hard-
  block others. Acceptable for the single-branch pilot; noted for multi-branch.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`delivery.read` / `delivery.manage` permissions. Rollback = revert the new files, the router entry,
and the nav link; no persisted client state.

## Open Questions

- Should `covered_zones` become a structured list (chips) rather than free text? Deferred — the
  backend stores a plain string; a structured field is a future backend+frontend change.
- Should the driver picker hard-restrict to the route's branch employees? Deferred — soft default
  now; revisit with the multi-branch phase.
