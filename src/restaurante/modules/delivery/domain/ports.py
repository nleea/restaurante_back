"""Ports (interfaces) of the Delivery module."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.delivery.domain.entities import (
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    OrderDelivery,
)


class DeliveryRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def order_exists(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool: ...

    # --- Branch delivery settings -------------------------------------------
    async def get_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting | None: ...

    async def create_settings(self, settings: DeliverySetting) -> DeliverySetting: ...

    async def update_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliverySetting | None: ...

    # --- Routes ------------------------------------------------------------
    async def create_route(self, route: DeliveryRoute) -> DeliveryRoute: ...

    async def next_route_position(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> int: ...

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
    async def create_route_driver(
        self, mapping: DeliveryRouteDriver
    ) -> DeliveryRouteDriver: ...

    async def route_driver_exists(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def is_active_driver_on_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

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
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[OrderDelivery]: ...

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None: ...

    # --- Runs --------------------------------------------------------------
    async def create_run(self, run: DeliveryRun) -> DeliveryRun: ...

    async def get_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> DeliveryRun | None: ...

    async def list_runs(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]: ...

    async def update_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRun | None: ...

    async def mark_run_deliveries_in_transit(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> None: ...
