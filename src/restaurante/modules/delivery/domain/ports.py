"""Ports (interfaces) of the Delivery module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.delivery.domain.entities import (
    ActiveRunTrail,
    DeliveryPaymentRequest,
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    DeliveryTariffBand,
    DistanceEstimate,
    GeoResult,
    OrderDelivery,
    OrderSummary,
    PaymentRequestView,
    RunPosition,
)


class Geocoder(Protocol):
    """Turns a written address into an approximate location, biased to a point.

    Implementations are best-effort: they return ``None`` on no match, error, or
    timeout (the caller keeps a null pin). The provider is swappable behind this port.
    """

    async def geocode(
        self,
        query: str,
        *,
        bias_lat: Decimal | None = None,
        bias_lon: Decimal | None = None,
    ) -> GeoResult | None: ...


class GeocodeQueue(Protocol):
    """Tells the resolver that one delivery needs a pin, so it lands in seconds.

    A hint, never a record of work. What needs a pin is the predicate over the rows
    (`DeliveryRepository.list_pending_geocode`), which the periodic pass reads and which stays
    authoritative. An announcement that is never sent, lost, or never delivered costs latency
    and nothing else — the pass still finds the record by its address and missing location.

    Because of that, `announce` SHALL NOT raise: it cannot be allowed to fail the operation
    that produced the record. Implementations swallow and log their own failures.
    """

    async def announce(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None: ...

    async def announce_quote(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
        """Ask the worker to price an already-pinned delivery now. SHALL NOT raise.

        Same contract as `announce`, different trigger: a delivery that arrived WITH
        coordinates never enters the geocoder, so nothing else would ever announce it.
        """
        ...


class DistanceEstimator(Protocol):
    """Swappable quote-distance source (local geodesic now, route gateway later)."""

    async def estimate(
        self,
        *,
        origin_lat: Decimal,
        origin_lon: Decimal,
        destination_lat: Decimal,
        destination_lon: Decimal,
    ) -> DistanceEstimate: ...


class OrderSettlement(Protocol):
    """Outbound port: cerrar la comanda que hay detrás de una entrega resuelta.

    Los dos desenlaces cierran. Entregada cierra bajo las reglas de siempre (cobrando el
    efectivo en la puerta si hace falta); no entregada cierra absorbiendo lo impagado como
    pérdida, porque el cliente no recibió nada y no puede quedar debiéndolo.

    Cerrar es además el único momento en que se descuenta inventario, y la comida se cocinó
    en ambos casos: dejar la comanda abierta haría que la despensa reportara stock que ya no
    existe.

    El adaptador concreto se cablea en el composition root, así que delivery depende de una
    interfaz y no del módulo orders.
    """

    async def settle_delivered(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        collected_by_employee_id: uuid.UUID | None = None,
    ) -> None:
        """Cobra el efectivo pendiente (si lo hay) y cierra. O ambas cosas, o ninguna."""
        ...

    async def settle_not_delivered(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
        """Cierra en modo write-off y deja constancia de la devolución si estaba pagada."""
        ...


class DeliveryRepository(Protocol):
    async def create_payment_request(
        self, request: DeliveryPaymentRequest
    ) -> DeliveryPaymentRequest:
        """Persist a request and hand back its id, keeping the caller's transient raw token.

        The raw token is NOT stored — only its hash — so the returned entity is the last place
        the readable link exists. Emitting it is the caller's job, right here.
        """
        ...

    async def get_payment_request_by_token(
        self, token_hash: str
    ) -> DeliveryPaymentRequest | None: ...

    async def payment_request_view(
        self, request: DeliveryPaymentRequest
    ) -> PaymentRequestView | None:
        """The customer-facing page for a request: order lines, money, and what is still due."""
        ...

    async def set_payment_method_for_request(
        self, request: DeliveryPaymentRequest, method: str
    ) -> None: ...

    async def record_payment_request_emission(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        emission_status: str,
        reason: str | None = None,
        emitted_at: datetime | None = None,
    ) -> None:
        """Write whether the link reached the customer. Never touches quote, fee or order."""
        ...

    async def invalidate_payment_requests_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> int:
        """Kill every still-usable request for a delivery, returning how many died."""
        ...

    async def payment_emissions_for_deliveries(
        self, tenant_id: uuid.UUID, delivery_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str | None]]:
        """Latest emission status/reason per delivery, batched. Empty for ones never emitted."""
        ...

    async def latest_payment_request_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> DeliveryPaymentRequest | None: ...

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        """The tenant's subdomain, needed to build a link that opens the right business."""
        ...

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool: ...

    async def employee_exists(self, tenant_id: uuid.UUID, employee_id: uuid.UUID) -> bool: ...

    async def order_branch(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> uuid.UUID | None: ...

    async def order_exists(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool: ...

    async def order_kitchen_state(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> str | None:
        """The order's derived kitchen readiness — the gate for assigning a delivery."""
        ...

    async def kitchen_states_for_orders(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...

    # --- Branch delivery settings -------------------------------------------
    async def get_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting | None: ...

    async def create_settings(self, settings: DeliverySetting) -> DeliverySetting: ...

    async def update_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliverySetting | None: ...

    async def list_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryTariffBand]: ...

    async def replace_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, bands: list[DeliveryTariffBand]
    ) -> list[DeliveryTariffBand]: ...

    # --- Routes ------------------------------------------------------------
    async def create_route(self, route: DeliveryRoute) -> DeliveryRoute: ...

    async def next_route_position(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> int: ...

    async def get_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> DeliveryRoute | None: ...

    async def list_routes(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryRoute]: ...

    async def update_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRoute | None: ...

    # --- Route drivers -----------------------------------------------------
    async def create_route_driver(self, mapping: DeliveryRouteDriver) -> DeliveryRouteDriver: ...

    async def route_driver_exists(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def is_active_driver_on_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def active_routes_for_driver(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[DeliveryRoute]:
        """Active routes the employee is an active driver of (for driver self-open)."""
        ...

    async def list_route_drivers(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> list[DeliveryRouteDriver]: ...

    async def delete_route_driver(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None: ...

    async def employees_with_active_runs(
        self, tenant_id: uuid.UUID, employee_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]: ...

    # --- Deliveries --------------------------------------------------------
    async def create_delivery(self, delivery: OrderDelivery) -> OrderDelivery: ...

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None: ...

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery | None: ...

    async def list_deliveries(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
        open_session_only: bool = False,
    ) -> list[OrderDelivery]: ...

    async def list_deliveries_for_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[OrderDelivery]:
        """A run's deliveries ordered by `route_position` (nulls last), then oldest first."""
        ...

    async def order_summaries(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, OrderSummary]:
        """Batched, read-only order projections keyed by order id (no N+1, no write path)."""
        ...

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None: ...

    async def apply_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        """Persist quote facts and the order's frozen delivery fee atomically."""
        ...

    async def list_pending_geocode(self, limit: int) -> list[OrderDelivery]:
        """Deliveries with an address but no pin, ACROSS EVERY TENANT, oldest first.

        The queue is this predicate, not a broker: a resolved pin leaves the set, a failure
        stays in it, and a restart loses nothing because the state is the row.

        Deliberately cross-tenant — the sweeper has no request, so no tenant context, so the
        automatic filter is skipped. That is what a sweeper needs and exactly the shape of a
        data leak, so it is named here: this returns other tenants' rows. It is only safe for
        a caller that answers no one. Never reach for it from the API.
        """
        ...

    async def list_pending_quotes(self, limit: int) -> list[OrderDelivery]: ...

    # --- Runs --------------------------------------------------------------
    async def create_run(self, run: DeliveryRun) -> DeliveryRun: ...

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun | None: ...

    async def active_run_for_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun | None:
        """The employee's single active (`preparing`/`in_transit`) run, if any."""
        ...

    async def list_runs(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]: ...

    async def update_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRun | None: ...

    async def mark_run_deliveries_in_transit(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> None: ...

    # --- Run positions (live driver trail) ---------------------------------
    async def append_position(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        branch_id: uuid.UUID,
        latitude: Decimal,
        longitude: Decimal,
    ) -> RunPosition:
        """Append one timestamped fix to a run's trail and return it."""
        ...

    async def run_trail(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> list[RunPosition]:
        """A run's trail ordered by `recorded_at` (oldest first)."""
        ...

    async def active_runs_positions(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[ActiveRunTrail]:
        """Per ACTIVE run (`preparing`/`in_transit`) in the branch with at least one fix:
        its employee and ordered trail (last point = current position)."""
        ...

    async def delete_run_positions(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
        """Prune a run's whole trail (called when the run finishes)."""
        ...
