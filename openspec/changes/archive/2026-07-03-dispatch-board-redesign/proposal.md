## Why

The Despacho screen redesign (three-pane dispatch board, approved as the design-only prototype at
`/dispatch/design`) gives dispatch operators at-a-glance state that the current two-column screen
lacks: live stats, per-stop run progress (the "stop strip"), time-pressure heat on overdue
domicilios, and a guided two-step run builder. The prototype runs on mock data; this change wires
it to the real delivery API and makes it *the* dispatch screen at `/dispatch`.

## What Changes

- **Backend (small):** add `created_at`/`updated_at` timestamps and a `notes` column to
  `order_deliveries` (`TimestampMixin` + migration); expose `created_at` on the delivery response
  and `created_at` on the run response; accept `notes` in the delivery PATCH. These unlock the
  design's "Recibido" timeline step, "hace N min" elapsed labels, heat glow, and per-domicilio
  notes.
- **Frontend:** port `DispatchDesignView` from mock state to the existing `dispatch`/`delivery`/
  `staff`/`orders` stores, keeping the approved layout and El Pase styling. UI adaptations agreed
  during exploration:
  - Per-delivery "Asignar conductor" becomes **"Asignar a despacho"** (pick a `preparing` run or
    create one) — the backend assigns drivers only through runs.
  - "Nuevo domicilio" modal selects an **open order** (`order_id` is required); route/driver fields
    are dropped from the form (route is set on assignment via the run).
  - "Cancelar" is offered only for `in_transit` deliveries (maps to `not_delivered`); the label is
    "No entregado".
  - "Salida estimada" is dropped (not stored); run cards show real `created_at`/`departed_at` times.
- **Replace:** `/dispatch` renders the new board; the old `DispatchPanel`/`DeliveriesArea`/
  `RunsArea` components, the mock module `dispatchDesignMock.ts`, and the `/dispatch/design` route
  are deleted.

## Capabilities

### New Capabilities

None — both affected capabilities already exist.

### Modified Capabilities

- `delivery-management`: delivery records gain persisted `created_at`/`updated_at` and an optional
  `notes` field editable via the existing PATCH; delivery and run read models expose `created_at`.
- `frontend-delivery-dispatch`: the DispatchView requirements change from the two-column
  list/detail to the three-pane board — stats summary, combined filters (status, route, driver,
  address search), delivery lifecycle timeline, run stop strip with per-stop progress, overdue
  heat indication, per-delivery notes, assign-to-run flow replacing direct driver assignment, and
  the two-step run creation modal. Existing lifecycle/permission requirements are preserved.

## Impact

- **Backend:** `modules/delivery/infrastructure/models.py` (mixin + notes), one Alembic migration,
  `infrastructure/api/schemas.py`, `application/use_cases/manage_delivery.py` (PATCH accepts
  notes), delivery tests.
- **Frontend:** `views/DispatchDesignView.vue` (becomes the wired board), `views/DispatchView.vue`
  (replaced), `components/dispatch/*` (deleted), `services/delivery.api.ts` (new fields),
  `stores/dispatch.ts` (minor getters), `router/index.ts` (route cleanup), unit tests.
- **Interplay:** the in-progress `delivery-address-picker` change targets the same "Nuevo
  domicilio" form (coordinate capture). This change keeps the form minimal (order + address +
  neighborhood + notes); the address picker lands on top of it afterwards — sequence, don't merge.
- **No breaking API changes** — only additive fields.
