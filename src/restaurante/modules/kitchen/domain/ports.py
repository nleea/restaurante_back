"""Ports (interfaces) of the Kitchen module."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.kitchen.domain.entities import (
    KitchenEvent,
    KitchenStation,
    OrderItemStation,
    ProductStation,
    StationSuggestion,
    StationTask,
    UnroutableProduct,
)


class KitchenEventPublisher(Protocol):
    """Outbound port: broadcast ticket changes to live kitchen screens.

    Implementations must be best-effort — publishing failures are the publisher's
    problem (log and swallow), never the mutation's.
    """

    async def publish(self, event: KitchenEvent) -> None: ...


class OrdersReadiness(Protocol):
    """Outbound port: push an order's derived kitchen readiness to the orders side.

    Symmetric to the orders `KitchenRouting` port. The concrete adapter is wired at the
    composition root so the kitchen application depends on an interface, not the orders module,
    preserving a one-way module dependency.
    """

    async def set_order_kitchen_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None: ...


class OrdersPaymentGate(Protocol):
    """Outbound port: ask the orders side whether an order's money is settled enough to cook.

    Prepaid orders (transfer, card, wallet) must have their payment verified before the kitchen
    starts, so the restaurant never cooks for money it has not confirmed. Cash orders always pass:
    their money arrives at the door.

    Kept as a port, like `OrdersReadiness`, so the kitchen depends on an interface rather than on
    the orders module.
    """

    async def may_cook(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool: ...


class KitchenRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def product_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> bool: ...

    async def station_exists(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool: ...

    async def order_exists(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool: ...

    # --- Stations ----------------------------------------------------------
    async def create_station(self, station: KitchenStation) -> KitchenStation: ...

    async def get_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStation | None: ...

    async def list_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[KitchenStation]: ...

    async def update_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID, fields: dict[str, Any]
    ) -> KitchenStation | None: ...

    # --- Product ↔ station -------------------------------------------------
    async def create_product_station(
        self, mapping: ProductStation
    ) -> ProductStation: ...

    async def product_station_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool: ...

    async def list_product_stations(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductStation]: ...

    async def variant_amounts(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        """Cuánto lleva esa variante de cada insumo, formateado para el pase."""
        ...

    async def suggest_product_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, product_id: uuid.UUID
    ) -> StationSuggestion | None:
        """Qué estaciones implica la receta del producto. ``None`` si el producto no existe."""
        ...

    async def list_unroutable_products(
        self, tenant_id: uuid.UUID
    ) -> list[UnroutableProduct]:
        """Los productos que ninguna estación prepara, con sus variantes activas."""
        ...

    async def list_stations_for_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, list[StationTask]]]: ...

    async def get_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID
    ) -> ProductStation | None: ...

    async def update_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductStation | None: ...

    async def delete_product_station(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> None: ...

    # --- Routing support ---------------------------------------------------
    async def variant_product_id(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def product_name(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> str | None:
        """El nombre del producto, para nombrar el que no llegó a la cocina."""
        ...

    async def list_non_cancelled_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]: ...

    async def ticket_exists(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool: ...

    async def create_ticket(self, ticket: OrderItemStation) -> OrderItemStation: ...

    # --- Ready rollup support ---------------------------------------------
    async def order_id_for_item(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def list_order_ticket_statuses(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[str]: ...

    # --- KDS board ---------------------------------------------------------
    async def list_tickets(
        self,
        tenant_id: uuid.UUID,
        station_id: uuid.UUID,
        *,
        status: str | None = None,
        open_session_only: bool = False,
    ) -> list[OrderItemStation]: ...

    async def get_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStation | None: ...

    async def update_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItemStation | None: ...
