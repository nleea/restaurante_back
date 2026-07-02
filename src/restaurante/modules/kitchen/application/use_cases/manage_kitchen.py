"""Application service for the Kitchen module (KDS).

Owns kitchen stations, product→station routing config, sending an order's items
to the line as tickets, and the KDS board lifecycle (`pending → in_progress →
ready`). Routing is idempotent; advancing is a strict forward state machine.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from restaurante.modules.kitchen.domain.entities import (
    KitchenEvent,
    KitchenStation,
    OrderItemStation,
    ProductStation,
)
from restaurante.modules.kitchen.domain.ports import (
    KitchenEventPublisher,
    KitchenRepository,
    OrdersReadiness,
)
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_READY = "ready"
STATUS_CANCELLED = "cancelled"

_NEXT_STATUS = {STATUS_PENDING: STATUS_IN_PROGRESS, STATUS_IN_PROGRESS: STATUS_READY}

# Itemized station tasks: bounded so a docket component stays glanceable.
MAX_TASKS_PER_MAPPING = 10
MAX_TASK_LENGTH = 60


def normalize_tasks(tasks: list[str]) -> list[str]:
    """Trim, drop empties, and bound the station task list (order preserved)."""
    cleaned = [t.strip() for t in tasks]
    cleaned = [t for t in cleaned if t]
    if len(cleaned) > MAX_TASKS_PER_MAPPING:
        raise ValidationError(
            f"Máximo {MAX_TASKS_PER_MAPPING} tareas por estación."
        )
    for task in cleaned:
        if len(task) > MAX_TASK_LENGTH:
            raise ValidationError(
                f"Cada tarea debe tener como máximo {MAX_TASK_LENGTH} caracteres."
            )
    return cleaned

# Order-level kitchen readiness derived from its tickets.
KITCHEN_STATE_NONE = "none"
KITCHEN_STATE_IN_KITCHEN = "in_kitchen"
KITCHEN_STATE_READY = "ready"


def derive_kitchen_state(ticket_statuses: list[str]) -> str:
    """Pure derivation of an order's kitchen readiness over its tickets.

    Tickets are the source of truth: `none` when the order has no (non-cancelled) ticket,
    `ready` when every non-cancelled ticket is `ready`, otherwise `in_kitchen`.
    """
    active = [s for s in ticket_statuses if s != STATUS_CANCELLED]
    if not active:
        return KITCHEN_STATE_NONE
    if all(s == STATUS_READY for s in active):
        return KITCHEN_STATE_READY
    return KITCHEN_STATE_IN_KITCHEN


class KitchenService:
    def __init__(
        self,
        repo: KitchenRepository,
        orders_readiness: OrdersReadiness | None = None,
        events: KitchenEventPublisher | None = None,
    ) -> None:
        self._repo = repo
        # Optional outbound ports: when wired, readiness transitions are pushed to the orders
        # side and ticket changes are broadcast to live KDS boards. Both are best-effort.
        self._orders_readiness = orders_readiness
        self._events = events

    # --- internal guards ---------------------------------------------------
    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        if not await self._repo.product_exists(tenant_id, product_id):
            raise NotFoundError(f"Producto no encontrado: {product_id}")

    async def _require_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStation:
        station = await self._repo.get_station(tenant_id, station_id)
        if station is None:
            raise NotFoundError(f"Estación no encontrada: {station_id}")
        return station

    async def _require_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStation:
        ticket = await self._repo.get_ticket(tenant_id, ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket no encontrado: {ticket_id}")
        return ticket

    # --- Stations ----------------------------------------------------------
    async def create_station(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, name: str, position: int
    ) -> KitchenStation:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.create_station(
            KitchenStation(
                tenant_id=tenant_id,
                branch_id=branch_id,
                name=name,
                position=position,
            )
        )

    async def list_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[KitchenStation]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_stations(tenant_id, branch_id)

    async def update_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID, fields: dict[str, Any]
    ) -> KitchenStation:
        updated = await self._repo.update_station(tenant_id, station_id, fields)
        if updated is None:
            raise NotFoundError(f"Estación no encontrada: {station_id}")
        return updated

    # --- Product ↔ station -------------------------------------------------
    async def attach_product_station(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        station_id: uuid.UUID,
        role: str | None = None,
        tasks: list[str] | None = None,
    ) -> ProductStation:
        await self._require_product(tenant_id, product_id)
        await self._require_station(tenant_id, station_id)
        if await self._repo.product_station_exists(tenant_id, product_id, station_id):
            raise ConflictError("El producto ya está asignado a esa estación.")
        return await self._repo.create_product_station(
            ProductStation(
                tenant_id=tenant_id,
                product_id=product_id,
                kitchen_station_id=station_id,
                role=role,
                tasks=normalize_tasks(tasks or []),
            )
        )

    async def update_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductStation:
        """Edit a mapping's role/tasks in place. Fired tickets keep their frozen copies —
        only orders routed after this edit carry the new values."""
        if "tasks" in fields and fields["tasks"] is not None:
            fields["tasks"] = normalize_tasks(fields["tasks"])
        updated = await self._repo.update_product_station(
            tenant_id, mapping_id, fields
        )
        if updated is None:
            raise NotFoundError(f"Asignación no encontrada: {mapping_id}")
        return updated

    async def list_product_stations(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductStation]:
        await self._require_product(tenant_id, product_id)
        return await self._repo.list_product_stations(tenant_id, product_id)

    async def detach_product_station(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> None:
        await self._repo.delete_product_station(tenant_id, product_id, station_id)

    # --- Routing -----------------------------------------------------------
    async def route_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderItemStation]:
        if not await self._repo.order_exists(tenant_id, order_id):
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        items = await self._repo.list_non_cancelled_items(tenant_id, order_id)
        created: list[OrderItemStation] = []
        for item_id, variant_id, branch_id in items:
            product_id = await self._repo.variant_product_id(tenant_id, variant_id)
            if product_id is None:
                continue
            station_roles = await self._repo.list_stations_for_product(
                tenant_id, product_id
            )
            for station_id, role, tasks in station_roles:
                # Idempotent: an existing ticket keeps the role/tasks captured at first route.
                if await self._repo.ticket_exists(tenant_id, item_id, station_id):
                    continue
                try:
                    created.append(
                        await self._repo.create_ticket(
                            OrderItemStation(
                                tenant_id=tenant_id,
                                branch_id=branch_id,
                                order_item_id=item_id,
                                kitchen_station_id=station_id,
                                role=role,
                                tasks=tasks,
                            )
                        )
                    )
                except ConflictError:
                    # A concurrent route won the (item, station) unique constraint —
                    # the ticket exists, which is exactly what we wanted. Converge.
                    continue
        # Recompute + push the order's kitchen readiness so a re-opened (previously ready) order
        # returns to `in_kitchen` once fresh pending tickets exist. Non-blocking side effect.
        await self._emit_kitchen_state(tenant_id, order_id)
        for ticket in created:
            await self._publish_event("ticket_created", ticket, order_id=order_id)
        return created

    # --- Ready rollup ------------------------------------------------------
    async def _compute_kitchen_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> str:
        statuses = await self._repo.list_order_ticket_statuses(tenant_id, order_id)
        return derive_kitchen_state(statuses)

    async def _emit_kitchen_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Best-effort push of the derived kitchen state to the orders side. A notify failure
        must never fail the caller (routing/advance), mirroring the orders→kitchen auto-route."""
        if self._orders_readiness is None:
            return
        try:
            state = await self._compute_kitchen_state(tenant_id, order_id)
            await self._orders_readiness.set_order_kitchen_state(
                tenant_id, order_id, state
            )
        except Exception:  # noqa: BLE001 - readiness notify is a non-blocking side effect
            pass

    # --- Live board events ---------------------------------------------------
    async def _publish_event(
        self,
        event_type: str,
        ticket: OrderItemStation,
        *,
        order_id: uuid.UUID | None = None,
    ) -> None:
        """Best-effort broadcast of a ticket change to live KDS boards. A publish failure
        must never fail the mutation, mirroring `_emit_kitchen_state`."""
        if self._events is None or ticket.id is None:
            return
        try:
            await self._events.publish(
                KitchenEvent(
                    type=event_type,
                    tenant_id=ticket.tenant_id,
                    branch_id=ticket.branch_id,
                    station_id=ticket.kitchen_station_id,
                    ticket_id=ticket.id,
                    status=ticket.status,
                    order_id=order_id,
                )
            )
        except Exception:  # noqa: BLE001 - board push is a non-blocking side effect
            pass

    # --- KDS board ---------------------------------------------------------
    async def list_tickets(
        self,
        tenant_id: uuid.UUID,
        station_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[OrderItemStation]:
        await self._require_station(tenant_id, station_id)
        return await self._repo.list_tickets(tenant_id, station_id, status=status)

    async def advance_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStation:
        ticket = await self._require_ticket(tenant_id, ticket_id)
        next_status = _NEXT_STATUS.get(ticket.status)
        if next_status is None:
            raise ConflictError(
                f"El ticket ya está en estado terminal: {ticket.status}."
            )
        fields: dict[str, Any] = {"status": next_status}
        if next_status == STATUS_READY:
            fields["ready_at"] = datetime.now(UTC)
        updated = await self._repo.update_ticket(tenant_id, ticket_id, fields)
        if updated is None:
            raise NotFoundError(f"Ticket no encontrado: {ticket_id}")
        # When a ticket reaches `ready`, recompute the order's readiness and push it to orders.
        # If this was the last non-ready ticket, the order flips to `ready`. Non-blocking.
        order_id: uuid.UUID | None = None
        if next_status == STATUS_READY:
            order_id = await self._repo.order_id_for_item(
                tenant_id, ticket.order_item_id
            )
            if order_id is not None:
                await self._emit_kitchen_state(tenant_id, order_id)
        await self._publish_event("ticket_advanced", updated, order_id=order_id)
        return updated
