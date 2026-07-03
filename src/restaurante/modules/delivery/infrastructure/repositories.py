"""Persistence adapter for the Delivery module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable). Unique-constraint violations are translated
to ``ConflictError``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.domain.entities import (
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    OrderDelivery,
)
from restaurante.modules.delivery.infrastructure.models import (
    DeliveryRouteDriverModel,
    DeliveryRouteModel,
    DeliveryRunModel,
    DeliverySettingModel,
    OrderDeliveryModel,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel

_ASSIGNED = "assigned"
_IN_TRANSIT = "in_transit"


def _route(m: DeliveryRouteModel) -> DeliveryRoute:
    return DeliveryRoute(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        name=m.name,
        zones=list(m.zones or []),
        color=m.color,
        position=m.position,
        is_active=m.is_active,
    )


def _settings(m: DeliverySettingModel) -> DeliverySetting:
    return DeliverySetting(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        latitude=m.latitude,
        longitude=m.longitude,
        ring_step_km=m.ring_step_km,
    )


def _route_driver(m: DeliveryRouteDriverModel) -> DeliveryRouteDriver:
    return DeliveryRouteDriver(
        id=m.id,
        tenant_id=m.tenant_id,
        delivery_route_id=m.delivery_route_id,
        employee_id=m.employee_id,
        is_active=m.is_active,
    )


def _run(m: DeliveryRunModel) -> DeliveryRun:
    return DeliveryRun(
        id=m.id,
        tenant_id=m.tenant_id,
        delivery_route_id=m.delivery_route_id,
        employee_id=m.employee_id,
        status=m.status,
        departed_at=m.departed_at,
        finished_at=m.finished_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _delivery(m: OrderDeliveryModel) -> OrderDelivery:
    return OrderDelivery(
        id=m.id,
        tenant_id=m.tenant_id,
        order_id=m.order_id,
        delivery_route_id=m.delivery_route_id,
        delivery_run_id=m.delivery_run_id,
        address_text=m.address_text,
        neighborhood=m.neighborhood,
        latitude=m.latitude,
        longitude=m.longitude,
        delivery_status=m.delivery_status,
        route_position=m.route_position,
        notes=m.notes,
        delivered_at=m.delivered_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def order_exists(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        stmt = select(OrderModel.id).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Branch delivery settings -------------------------------------------
    async def get_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> DeliverySetting | None:
        stmt = select(DeliverySettingModel).where(
            DeliverySettingModel.tenant_id == tenant_id,
            DeliverySettingModel.branch_id == branch_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _settings(model) if model else None

    async def create_settings(self, settings: DeliverySetting) -> DeliverySetting:
        model = DeliverySettingModel(
            tenant_id=settings.tenant_id,
            branch_id=settings.branch_id,
            latitude=settings.latitude,
            longitude=settings.longitude,
            ring_step_km=settings.ring_step_km,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError:
            # A concurrent first-read already created the branch row — converge on it.
            await self._session.rollback()
            existing = await self.get_settings_by_branch(
                settings.tenant_id, settings.branch_id
            )
            assert existing is not None
            return existing
        await self._session.refresh(model)
        return _settings(model)

    async def update_settings_by_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliverySetting | None:
        stmt = select(DeliverySettingModel).where(
            DeliverySettingModel.tenant_id == tenant_id,
            DeliverySettingModel.branch_id == branch_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _settings(model)

    # --- Routes ------------------------------------------------------------
    async def create_route(self, route: DeliveryRoute) -> DeliveryRoute:
        model = DeliveryRouteModel(
            tenant_id=route.tenant_id,
            branch_id=route.branch_id,
            name=route.name,
            zones=route.zones,
            color=route.color,
            position=route.position,
            is_active=route.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _route(model)

    async def next_route_position(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> int:
        stmt = select(func.max(DeliveryRouteModel.position)).where(
            DeliveryRouteModel.tenant_id == tenant_id,
            DeliveryRouteModel.branch_id == branch_id,
        )
        current = (await self._session.execute(stmt)).scalar_one_or_none()
        return 0 if current is None else current + 1

    async def _get_route_model(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> DeliveryRouteModel | None:
        stmt = select(DeliveryRouteModel).where(
            DeliveryRouteModel.id == route_id,
            DeliveryRouteModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> DeliveryRoute | None:
        model = await self._get_route_model(tenant_id, route_id)
        return _route(model) if model else None

    async def list_routes(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryRoute]:
        stmt = (
            select(DeliveryRouteModel)
            .where(
                DeliveryRouteModel.tenant_id == tenant_id,
                DeliveryRouteModel.branch_id == branch_id,
            )
            .order_by(DeliveryRouteModel.position, DeliveryRouteModel.name)
        )
        return [_route(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRoute | None:
        model = await self._get_route_model(tenant_id, route_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _route(model)

    # --- Route drivers -----------------------------------------------------
    async def create_route_driver(
        self, mapping: DeliveryRouteDriver
    ) -> DeliveryRouteDriver:
        model = DeliveryRouteDriverModel(
            tenant_id=mapping.tenant_id,
            delivery_route_id=mapping.delivery_route_id,
            employee_id=mapping.employee_id,
            is_active=mapping.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "El repartidor ya está asignado a esa ruta."
            ) from exc
        await self._session.refresh(model)
        return _route_driver(model)

    async def route_driver_exists(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(DeliveryRouteDriverModel.id).where(
            DeliveryRouteDriverModel.tenant_id == tenant_id,
            DeliveryRouteDriverModel.delivery_route_id == route_id,
            DeliveryRouteDriverModel.employee_id == employee_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def is_active_driver_on_route(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(DeliveryRouteDriverModel.id).where(
            DeliveryRouteDriverModel.tenant_id == tenant_id,
            DeliveryRouteDriverModel.delivery_route_id == route_id,
            DeliveryRouteDriverModel.employee_id == employee_id,
            DeliveryRouteDriverModel.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_route_drivers(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> list[DeliveryRouteDriver]:
        stmt = select(DeliveryRouteDriverModel).where(
            DeliveryRouteDriverModel.tenant_id == tenant_id,
            DeliveryRouteDriverModel.delivery_route_id == route_id,
        )
        return [
            _route_driver(m) for m in (await self._session.execute(stmt)).scalars()
        ]

    async def delete_route_driver(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(DeliveryRouteDriverModel).where(
                DeliveryRouteDriverModel.tenant_id == tenant_id,
                DeliveryRouteDriverModel.delivery_route_id == route_id,
                DeliveryRouteDriverModel.employee_id == employee_id,
            )
        )
        await self._session.commit()

    async def employees_with_active_runs(
        self, tenant_id: uuid.UUID, employee_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not employee_ids:
            return set()
        stmt = select(DeliveryRunModel.employee_id).where(
            DeliveryRunModel.tenant_id == tenant_id,
            DeliveryRunModel.employee_id.in_(employee_ids),
            DeliveryRunModel.status.in_(("preparing", "in_transit")),
        )
        return {row[0] for row in (await self._session.execute(stmt)).all()}

    # --- Deliveries --------------------------------------------------------
    async def create_delivery(self, delivery: OrderDelivery) -> OrderDelivery:
        model = OrderDeliveryModel(
            tenant_id=delivery.tenant_id,
            order_id=delivery.order_id,
            delivery_route_id=delivery.delivery_route_id,
            delivery_run_id=delivery.delivery_run_id,
            address_text=delivery.address_text,
            neighborhood=delivery.neighborhood,
            latitude=delivery.latitude,
            longitude=delivery.longitude,
            delivery_status=delivery.delivery_status,
            route_position=delivery.route_position,
            notes=delivery.notes,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("La orden ya tiene un registro de entrega.") from exc
        await self._session.refresh(model)
        return _delivery(model)

    async def _get_delivery_model(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDeliveryModel | None:
        stmt = select(OrderDeliveryModel).where(
            OrderDeliveryModel.id == delivery_id,
            OrderDeliveryModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None:
        model = await self._get_delivery_model(tenant_id, delivery_id)
        return _delivery(model) if model else None

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery | None:
        stmt = select(OrderDeliveryModel).where(
            OrderDeliveryModel.tenant_id == tenant_id,
            OrderDeliveryModel.order_id == order_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _delivery(model) if model else None

    async def list_deliveries(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[OrderDelivery]:
        stmt = select(OrderDeliveryModel).where(
            OrderDeliveryModel.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(OrderDeliveryModel.delivery_status == status)
        return [_delivery(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        model = await self._get_delivery_model(tenant_id, delivery_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _delivery(model)

    # --- Runs --------------------------------------------------------------
    async def create_run(self, run: DeliveryRun) -> DeliveryRun:
        model = DeliveryRunModel(
            tenant_id=run.tenant_id,
            delivery_route_id=run.delivery_route_id,
            employee_id=run.employee_id,
            status=run.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _run(model)

    async def _get_run_model(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> DeliveryRunModel | None:
        stmt = select(DeliveryRunModel).where(
            DeliveryRunModel.id == run_id, DeliveryRunModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> DeliveryRun | None:
        model = await self._get_run_model(tenant_id, run_id)
        return _run(model) if model else None

    async def list_runs(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]:
        stmt = select(DeliveryRunModel).where(DeliveryRunModel.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(DeliveryRunModel.status == status)
        stmt = stmt.order_by(DeliveryRunModel.created_at.desc())
        return [_run(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, fields: dict[str, Any]
    ) -> DeliveryRun | None:
        model = await self._get_run_model(tenant_id, run_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _run(model)

    async def mark_run_deliveries_in_transit(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            update(OrderDeliveryModel)
            .where(
                OrderDeliveryModel.tenant_id == tenant_id,
                OrderDeliveryModel.delivery_run_id == run_id,
                OrderDeliveryModel.delivery_status == _ASSIGNED,
            )
            .values(delivery_status=_IN_TRANSIT)
        )
        await self._session.commit()
