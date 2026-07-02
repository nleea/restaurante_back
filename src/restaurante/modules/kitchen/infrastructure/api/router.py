"""Kitchen API: stations, product→station routing, order routing, KDS board.

RBAC: reads `kitchen.read`; writes (manage stations, configure routing, route an
order, advance tickets) `kitchen.update`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.kitchen.infrastructure.api.deps import (
    EventStreamDep,
    KitchenServiceDep,
    TenantDep,
)
from restaurante.modules.kitchen.infrastructure.api.schemas import (
    AttachProductStationRequest,
    CreateStationRequest,
    KitchenStationResponse,
    ProductStationResponse,
    TicketResponse,
    UpdateProductStationRequest,
    UpdateStationRequest,
)

router = APIRouter(prefix="/kitchen", tags=["kitchen"])

_READ = Depends(require_permission("kitchen.read"))
_WRITE = Depends(require_permission("kitchen.update"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Stations ---------------------------------------------------------------
@router.post(
    "/stations",
    response_model=KitchenStationResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_station(
    payload: CreateStationRequest, service: KitchenServiceDep, tenant_id: TenantDep
) -> KitchenStationResponse:
    station = await service.create_station(
        tenant_id, payload.branch_id, payload.name, payload.position
    )
    return KitchenStationResponse.model_validate(station, from_attributes=True)


@router.get(
    "/stations", response_model=list[KitchenStationResponse], dependencies=[_READ]
)
async def list_stations(
    branch_id: uuid.UUID, service: KitchenServiceDep, tenant_id: TenantDep
) -> list[KitchenStationResponse]:
    stations = await service.list_stations(tenant_id, branch_id)
    return [
        KitchenStationResponse.model_validate(s, from_attributes=True)
        for s in stations
    ]


@router.patch(
    "/stations/{station_id}",
    response_model=KitchenStationResponse,
    dependencies=[_WRITE],
)
async def update_station(
    station_id: uuid.UUID,
    payload: UpdateStationRequest,
    service: KitchenServiceDep,
    tenant_id: TenantDep,
) -> KitchenStationResponse:
    station = await service.update_station(
        tenant_id, station_id, payload.model_dump(exclude_unset=True)
    )
    return KitchenStationResponse.model_validate(station, from_attributes=True)


# --- Product ↔ station -------------------------------------------------------
@router.post(
    "/product-stations",
    response_model=ProductStationResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def attach_product_station(
    payload: AttachProductStationRequest,
    service: KitchenServiceDep,
    tenant_id: TenantDep,
) -> ProductStationResponse:
    mapping = await service.attach_product_station(
        tenant_id,
        payload.product_id,
        payload.kitchen_station_id,
        payload.role,
        tasks=list(payload.tasks),
    )
    return ProductStationResponse.model_validate(mapping, from_attributes=True)


@router.patch(
    "/product-stations/{mapping_id}",
    response_model=ProductStationResponse,
    dependencies=[_WRITE],
)
async def update_product_station(
    mapping_id: uuid.UUID,
    payload: UpdateProductStationRequest,
    service: KitchenServiceDep,
    tenant_id: TenantDep,
) -> ProductStationResponse:
    """Edit a mapping's role/tasks in place — already-fired tickets keep their frozen copies."""
    mapping = await service.update_product_station(
        tenant_id, mapping_id, payload.model_dump(exclude_unset=True)
    )
    return ProductStationResponse.model_validate(mapping, from_attributes=True)


@router.get(
    "/products/{product_id}/stations",
    response_model=list[ProductStationResponse],
    dependencies=[_READ],
)
async def list_product_stations(
    product_id: uuid.UUID, service: KitchenServiceDep, tenant_id: TenantDep
) -> list[ProductStationResponse]:
    mappings = await service.list_product_stations(tenant_id, product_id)
    return [
        ProductStationResponse.model_validate(m, from_attributes=True)
        for m in mappings
    ]


@router.delete(
    "/products/{product_id}/stations/{station_id}",
    status_code=_NO_CONTENT,
    dependencies=[_WRITE],
)
async def detach_product_station(
    product_id: uuid.UUID,
    station_id: uuid.UUID,
    service: KitchenServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.detach_product_station(tenant_id, product_id, station_id)
    return Response(status_code=_NO_CONTENT)


# --- Routing + board --------------------------------------------------------
@router.post(
    "/orders/{order_id}/route",
    response_model=list[TicketResponse],
    status_code=201,
    dependencies=[_WRITE],
)
async def route_order(
    order_id: uuid.UUID, service: KitchenServiceDep, tenant_id: TenantDep
) -> list[TicketResponse]:
    tickets = await service.route_order(tenant_id, order_id)
    return [TicketResponse.model_validate(t, from_attributes=True) for t in tickets]


@router.get(
    "/stations/{station_id}/tickets",
    response_model=list[TicketResponse],
    dependencies=[_READ],
)
async def list_tickets(
    station_id: uuid.UUID,
    service: KitchenServiceDep,
    tenant_id: TenantDep,
    status_filter: str | None = None,
) -> list[TicketResponse]:
    tickets = await service.list_tickets(tenant_id, station_id, status=status_filter)
    return [TicketResponse.model_validate(t, from_attributes=True) for t in tickets]


@router.post(
    "/tickets/{ticket_id}/advance",
    response_model=TicketResponse,
    dependencies=[_WRITE],
)
async def advance_ticket(
    ticket_id: uuid.UUID, service: KitchenServiceDep, tenant_id: TenantDep
) -> TicketResponse:
    ticket = await service.advance_ticket(tenant_id, ticket_id)
    return TicketResponse.model_validate(ticket, from_attributes=True)


# --- Live board (SSE) ---------------------------------------------------------
@router.get("/events", dependencies=[_READ])
async def stream_events(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """Server-sent events with the branch's ticket changes (heartbeat every ~15 s).

    Degrades to heartbeats-only when the broker is down, so clients can keep the
    connection and fall back to polling for data freshness.
    """
    return StreamingResponse(
        stream.frames(tenant_id, branch_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
