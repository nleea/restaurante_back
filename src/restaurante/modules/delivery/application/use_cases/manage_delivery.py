"""Application service for the Delivery module (own fleet).

Owns routes, route drivers, per-order delivery records, dispatch runs, and the
explicit lifecycle: assign → depart → deliver → finish. Two forward-only state
machines (delivery and run) with guarded transitions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from restaurante.modules.delivery.domain.entities import (
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    OrderDelivery,
)
from restaurante.modules.delivery.domain.ports import DeliveryRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

# Delivery states
D_PENDING = "pending"
D_ASSIGNED = "assigned"
D_IN_TRANSIT = "in_transit"
D_DELIVERED = "delivered"
D_NOT_DELIVERED = "not_delivered"

# Run states
R_PREPARING = "preparing"
R_IN_TRANSIT = "in_transit"
R_FINISHED = "finished"

# Derived driver status for the coverage map (never stored).
DRIVER_ON_ROUTE = "on_route"
DRIVER_AVAILABLE = "available"
DRIVER_INACTIVE = "inactive"

# Coverage-map bounds
MAX_ZONES_PER_ROUTE = 20
MAX_ZONE_LENGTH = 60
RING_STEP_MIN = Decimal("0.5")
RING_STEP_MAX = Decimal("5.0")


def normalize_zones(zones: list[str]) -> list[str]:
    """Trim, drop empties, and bound the route's zone-name list (order preserved)."""
    cleaned = [z.strip() for z in zones]
    cleaned = [z for z in cleaned if z]
    if len(cleaned) > MAX_ZONES_PER_ROUTE:
        raise ValidationError(f"Máximo {MAX_ZONES_PER_ROUTE} zonas por ruta.")
    for zone in cleaned:
        if len(zone) > MAX_ZONE_LENGTH:
            raise ValidationError(
                f"Cada zona debe tener como máximo {MAX_ZONE_LENGTH} caracteres."
            )
    return cleaned


class DeliveryService:
    def __init__(self, repo: DeliveryRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> DeliveryRoute:
        route = await self._repo.get_route(tenant_id, route_id)
        if route is None:
            raise NotFoundError(f"Ruta no encontrada: {route_id}")
        return route

    async def _require_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> DeliveryRun:
        run = await self._repo.get_run(tenant_id, run_id)
        if run is None:
            raise NotFoundError(f"Despacho no encontrado: {run_id}")
        return run

    async def _require_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery:
        delivery = await self._repo.get_delivery(tenant_id, delivery_id)
        if delivery is None:
            raise NotFoundError(f"Entrega no encontrada: {delivery_id}")
        return delivery

    # --- Branch delivery settings -------------------------------------------
    async def get_settings(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting:
        """Lazy-create the branch's settings so clients always receive one shape
        (null coordinates = the business pin hasn't been placed yet)."""
        await self._require_branch(tenant_id, branch_id)
        settings = await self._repo.get_settings_by_branch(tenant_id, branch_id)
        if settings is not None:
            return settings
        return await self._repo.create_settings(
            DeliverySetting(tenant_id=tenant_id, branch_id=branch_id)
        )

    async def update_settings(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliverySetting:
        step = fields.get("ring_step_km")
        if step is not None and not (RING_STEP_MIN <= step <= RING_STEP_MAX):
            raise ValidationError(
                f"El radio por ruta debe estar entre {RING_STEP_MIN} y {RING_STEP_MAX} km."
            )
        await self.get_settings(tenant_id, branch_id)  # ensure the row exists
        updated = await self._repo.update_settings_by_branch(
            tenant_id, branch_id, fields
        )
        assert updated is not None
        return updated

    # --- Routes ------------------------------------------------------------
    async def create_route(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        name: str,
        zones: list[str] | None = None,
        color: str | None = None,
    ) -> DeliveryRoute:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.create_route(
            DeliveryRoute(
                tenant_id=tenant_id,
                branch_id=branch_id,
                name=name,
                zones=normalize_zones(zones or []),
                color=color,
                # The new ring takes the branch's next band.
                position=await self._repo.next_route_position(tenant_id, branch_id),
            )
        )

    async def list_routes(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryRoute]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_routes(tenant_id, branch_id)

    async def update_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRoute:
        if "zones" in fields and fields["zones"] is not None:
            fields["zones"] = normalize_zones(fields["zones"])
        updated = await self._repo.update_route(tenant_id, route_id, fields)
        if updated is None:
            raise NotFoundError(f"Ruta no encontrada: {route_id}")
        return updated

    # --- Route drivers -----------------------------------------------------
    async def attach_route_driver(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> tuple[DeliveryRouteDriver, str]:
        await self._require_route(tenant_id, route_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        if await self._repo.route_driver_exists(tenant_id, route_id, employee_id):
            raise ConflictError("El repartidor ya está asignado a esa ruta.")
        mapping = await self._repo.create_route_driver(
            DeliveryRouteDriver(
                tenant_id=tenant_id,
                delivery_route_id=route_id,
                employee_id=employee_id,
            )
        )
        riding = await self._repo.employees_with_active_runs(tenant_id, [employee_id])
        status = DRIVER_ON_ROUTE if employee_id in riding else DRIVER_AVAILABLE
        return mapping, status

    async def list_route_drivers(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> list[tuple[DeliveryRouteDriver, str]]:
        """The route's drivers with their DERIVED status: `inactive` (assignment off),
        `on_route` (has a run in preparing/in_transit), else `available`. Read-only —
        the dispatch lifecycle already produces the underlying facts."""
        await self._require_route(tenant_id, route_id)
        drivers = await self._repo.list_route_drivers(tenant_id, route_id)
        riding = await self._repo.employees_with_active_runs(
            tenant_id, [d.employee_id for d in drivers]
        )

        def status(driver: DeliveryRouteDriver) -> str:
            if not driver.is_active:
                return DRIVER_INACTIVE
            return DRIVER_ON_ROUTE if driver.employee_id in riding else DRIVER_AVAILABLE

        return [(d, status(d)) for d in drivers]

    async def detach_route_driver(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        await self._repo.delete_route_driver(tenant_id, route_id, employee_id)

    # --- Deliveries --------------------------------------------------------
    async def create_delivery(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        address_text: str,
        neighborhood: str | None = None,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
    ) -> OrderDelivery:
        if not await self._repo.order_exists(tenant_id, order_id):
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        if await self._repo.get_delivery_by_order(tenant_id, order_id) is not None:
            raise ConflictError("La orden ya tiene un registro de entrega.")
        return await self._repo.create_delivery(
            OrderDelivery(
                tenant_id=tenant_id,
                order_id=order_id,
                address_text=address_text,
                neighborhood=neighborhood,
                latitude=latitude,
                longitude=longitude,
            )
        )

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery:
        delivery = await self._repo.get_delivery_by_order(tenant_id, order_id)
        if delivery is None:
            raise NotFoundError(f"Entrega no encontrada para la orden: {order_id}")
        return delivery

    async def list_deliveries(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[OrderDelivery]:
        return await self._repo.list_deliveries(tenant_id, status=status)

    async def update_delivery_address(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery:
        await self._require_delivery(tenant_id, delivery_id)
        updated = await self._repo.update_delivery(tenant_id, delivery_id, fields)
        if updated is None:
            raise NotFoundError(f"Entrega no encontrada: {delivery_id}")
        return updated

    # --- Runs --------------------------------------------------------------
    async def create_run(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun:
        await self._require_route(tenant_id, route_id)
        if not await self._repo.is_active_driver_on_route(
            tenant_id, route_id, employee_id
        ):
            raise ValidationError(
                "El empleado no es un repartidor activo de esa ruta."
            )
        return await self._repo.create_run(
            DeliveryRun(
                tenant_id=tenant_id,
                delivery_route_id=route_id,
                employee_id=employee_id,
            )
        )

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        return await self._require_run(tenant_id, run_id)

    async def list_runs(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]:
        return await self._repo.list_runs(tenant_id, status=status)

    # --- Lifecycle ---------------------------------------------------------
    async def assign_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, run_id: uuid.UUID
    ) -> OrderDelivery:
        delivery = await self._require_delivery(tenant_id, delivery_id)
        run = await self._require_run(tenant_id, run_id)
        if run.status != R_PREPARING:
            raise ConflictError(
                f"El despacho no está en preparación (estado: {run.status})."
            )
        if delivery.delivery_status not in (D_PENDING, D_ASSIGNED):
            raise ConflictError(
                f"La entrega no se puede asignar (estado: {delivery.delivery_status})."
            )
        updated = await self._repo.update_delivery(
            tenant_id,
            delivery_id,
            {
                "delivery_run_id": run_id,
                "delivery_route_id": run.delivery_route_id,
                "delivery_status": D_ASSIGNED,
            },
        )
        assert updated is not None
        return updated

    async def depart_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        run = await self._require_run(tenant_id, run_id)
        if run.status != R_PREPARING:
            raise ConflictError(
                f"El despacho no está en preparación (estado: {run.status})."
            )
        await self._repo.mark_run_deliveries_in_transit(tenant_id, run_id)
        updated = await self._repo.update_run(
            tenant_id,
            run_id,
            {"status": R_IN_TRANSIT, "departed_at": datetime.now(UTC)},
        )
        assert updated is not None
        return updated

    async def mark_delivered(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, delivered: bool
    ) -> OrderDelivery:
        delivery = await self._require_delivery(tenant_id, delivery_id)
        if delivery.delivery_status != D_IN_TRANSIT:
            raise ConflictError(
                "La entrega debe estar en camino para marcar el resultado "
                f"(estado: {delivery.delivery_status})."
            )
        new_status = D_DELIVERED if delivered else D_NOT_DELIVERED
        updated = await self._repo.update_delivery(
            tenant_id,
            delivery_id,
            {"delivery_status": new_status, "delivered_at": datetime.now(UTC)},
        )
        assert updated is not None
        return updated

    async def finish_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        run = await self._require_run(tenant_id, run_id)
        if run.status != R_IN_TRANSIT:
            raise ConflictError(
                f"El despacho no está en camino (estado: {run.status})."
            )
        updated = await self._repo.update_run(
            tenant_id,
            run_id,
            {"status": R_FINISHED, "finished_at": datetime.now(UTC)},
        )
        assert updated is not None
        return updated
