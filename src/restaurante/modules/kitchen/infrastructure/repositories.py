"""Persistence adapter for the Kitchen module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable). Reads into menu/orders tables support
routing an order's items to stations.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.kitchen.domain.entities import (
    KitchenStation,
    OrderItemStation,
    ProductStation,
)
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
)
from restaurante.modules.menu.infrastructure.models import (
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel

_CANCELLED = "cancelled"


def _station(m: KitchenStationModel) -> KitchenStation:
    return KitchenStation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        name=m.name,
        position=m.position,
        is_active=m.is_active,
    )


def _product_station(m: ProductStationModel) -> ProductStation:
    return ProductStation(
        id=m.id,
        tenant_id=m.tenant_id,
        product_id=m.product_id,
        kitchen_station_id=m.kitchen_station_id,
        role=m.role,
        tasks=list(m.tasks or []),
    )


def _ticket(m: OrderItemStationModel) -> OrderItemStation:
    return OrderItemStation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_item_id=m.order_item_id,
        kitchen_station_id=m.kitchen_station_id,
        status=m.status,
        role=m.role,
        tasks=list(m.tasks or []),
        ready_at=m.ready_at,
        entered_at=m.entered_at,
    )


class SqlAlchemyKitchenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def product_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductModel.id).where(
            ProductModel.id == product_id, ProductModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def station_exists(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(KitchenStationModel.id).where(
            KitchenStationModel.id == station_id,
            KitchenStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def order_exists(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        stmt = select(OrderModel.id).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Stations ----------------------------------------------------------
    async def create_station(self, station: KitchenStation) -> KitchenStation:
        model = KitchenStationModel(
            tenant_id=station.tenant_id,
            branch_id=station.branch_id,
            name=station.name,
            position=station.position,
            is_active=station.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _station(model)

    async def _get_station_model(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStationModel | None:
        stmt = select(KitchenStationModel).where(
            KitchenStationModel.id == station_id,
            KitchenStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStation | None:
        model = await self._get_station_model(tenant_id, station_id)
        return _station(model) if model else None

    async def list_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[KitchenStation]:
        stmt = (
            select(KitchenStationModel)
            .where(
                KitchenStationModel.tenant_id == tenant_id,
                KitchenStationModel.branch_id == branch_id,
            )
            .order_by(KitchenStationModel.position, KitchenStationModel.name)
        )
        return [_station(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID, fields: dict[str, Any]
    ) -> KitchenStation | None:
        model = await self._get_station_model(tenant_id, station_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _station(model)

    # --- Product ↔ station -------------------------------------------------
    async def create_product_station(
        self, mapping: ProductStation
    ) -> ProductStation:
        model = ProductStationModel(
            tenant_id=mapping.tenant_id,
            product_id=mapping.product_id,
            kitchen_station_id=mapping.kitchen_station_id,
            role=mapping.role,
            tasks=mapping.tasks,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "El producto ya está asignado a esa estación."
            ) from exc
        await self._session.refresh(model)
        return _product_station(model)

    async def product_station_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductStationModel.id).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
            ProductStationModel.kitchen_station_id == station_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_product_stations(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductStation]:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
        )
        return [
            _product_station(m) for m in (await self._session.execute(stmt)).scalars()
        ]

    async def list_stations_for_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, list[str]]]:
        stmt = select(
            ProductStationModel.kitchen_station_id,
            ProductStationModel.role,
            ProductStationModel.tasks,
        ).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
        )
        return [
            (row[0], row[1], list(row[2] or []))
            for row in (await self._session.execute(stmt)).all()
        ]

    async def get_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID
    ) -> ProductStation | None:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.id == mapping_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _product_station(model) if model else None

    async def update_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductStation | None:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.id == mapping_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _product_station(model)

    async def delete_product_station(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(ProductStationModel).where(
                ProductStationModel.tenant_id == tenant_id,
                ProductStationModel.product_id == product_id,
                ProductStationModel.kitchen_station_id == station_id,
            )
        )
        await self._session.commit()

    # --- Routing support ---------------------------------------------------
    async def variant_product_id(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(ProductVariantModel.product_id).where(
            ProductVariantModel.id == variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_non_cancelled_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
        stmt = select(
            OrderItemModel.id,
            OrderItemModel.product_variant_id,
            OrderItemModel.branch_id,
        ).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id == order_id,
            OrderItemModel.status != _CANCELLED,
        )
        return [
            (row[0], row[1], row[2])
            for row in (await self._session.execute(stmt)).all()
        ]

    async def ticket_exists(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(OrderItemStationModel.id).where(
            OrderItemStationModel.tenant_id == tenant_id,
            OrderItemStationModel.order_item_id == order_item_id,
            OrderItemStationModel.kitchen_station_id == station_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def create_ticket(self, ticket: OrderItemStation) -> OrderItemStation:
        model = OrderItemStationModel(
            tenant_id=ticket.tenant_id,
            branch_id=ticket.branch_id,
            order_item_id=ticket.order_item_id,
            kitchen_station_id=ticket.kitchen_station_id,
            status=ticket.status,
            role=ticket.role,
            tasks=ticket.tasks,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # The (order_item, station) unique constraint fired: a concurrent route already
            # created this ticket. Surface it as a conflict so the caller can skip it.
            await self._session.rollback()
            raise ConflictError("El ítem ya está ruteado a esa estación.") from exc
        await self._session.refresh(model)
        return _ticket(model)

    # --- Ready rollup support ----------------------------------------------
    async def order_id_for_item(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(OrderItemModel.order_id).where(
            OrderItemModel.id == order_item_id,
            OrderItemModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_order_ticket_statuses(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[str]:
        stmt = (
            select(OrderItemStationModel.status)
            .join(
                OrderItemModel,
                OrderItemModel.id == OrderItemStationModel.order_item_id,
            )
            .where(
                OrderItemStationModel.tenant_id == tenant_id,
                OrderItemModel.order_id == order_id,
            )
        )
        return list((await self._session.execute(stmt)).scalars())

    # --- KDS board ---------------------------------------------------------
    async def list_tickets(
        self,
        tenant_id: uuid.UUID,
        station_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[OrderItemStation]:
        stmt = select(OrderItemStationModel).where(
            OrderItemStationModel.tenant_id == tenant_id,
            OrderItemStationModel.kitchen_station_id == station_id,
        )
        if status is not None:
            stmt = stmt.where(OrderItemStationModel.status == status)
        stmt = stmt.order_by(OrderItemStationModel.entered_at)
        return [_ticket(m) for m in (await self._session.execute(stmt)).scalars()]

    async def _get_ticket_model(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStationModel | None:
        stmt = select(OrderItemStationModel).where(
            OrderItemStationModel.id == ticket_id,
            OrderItemStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStation | None:
        model = await self._get_ticket_model(tenant_id, ticket_id)
        return _ticket(model) if model else None

    async def update_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItemStation | None:
        model = await self._get_ticket_model(tenant_id, ticket_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _ticket(model)
