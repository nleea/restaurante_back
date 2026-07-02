"""Delivery API: own-fleet routes, drivers, deliveries, runs and lifecycle.

RBAC: reads `delivery.read`; configuration/creation `delivery.manage`; operational
lifecycle (assign, depart, mark delivered, finish) `delivery.assign`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.delivery.infrastructure.api.deps import (
    DeliveryServiceDep,
    TenantDep,
)
from restaurante.modules.delivery.infrastructure.api.schemas import (
    AssignDeliveryRequest,
    AttachRouteDriverRequest,
    CreateDeliveryRequest,
    CreateRouteRequest,
    CreateRunRequest,
    DeliveryResponse,
    DeliverySettingsResponse,
    MarkDeliveredRequest,
    RouteDriverResponse,
    RouteResponse,
    RunResponse,
    UpdateDeliveryAddressRequest,
    UpdateDeliverySettingsRequest,
    UpdateRouteRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/delivery", tags=["delivery"])

_READ = Depends(require_permission("delivery.read"))
_MANAGE = Depends(require_permission("delivery.manage"))
_ASSIGN = Depends(require_permission("delivery.assign"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Branch delivery settings -------------------------------------------------
@router.get(
    "/branches/{branch_id}/settings",
    response_model=DeliverySettingsResponse,
    dependencies=[_READ],
)
async def get_delivery_settings(
    branch_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> DeliverySettingsResponse:
    """Lazy-creates the default row; null coordinates mean the pin isn't placed yet."""
    settings = await service.get_settings(tenant_id, branch_id)
    return DeliverySettingsResponse.model_validate(settings, from_attributes=True)


@router.patch(
    "/branches/{branch_id}/settings",
    response_model=DeliverySettingsResponse,
    dependencies=[_MANAGE],
)
async def update_delivery_settings(
    branch_id: uuid.UUID,
    payload: UpdateDeliverySettingsRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> DeliverySettingsResponse:
    settings = await service.update_settings(
        tenant_id, branch_id, payload.model_dump(exclude_unset=True)
    )
    return DeliverySettingsResponse.model_validate(settings, from_attributes=True)


# --- Routes -----------------------------------------------------------------
@router.post(
    "/routes", response_model=RouteResponse, status_code=201, dependencies=[_MANAGE]
)
async def create_route(
    payload: CreateRouteRequest, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RouteResponse:
    route = await service.create_route(
        tenant_id,
        payload.branch_id,
        payload.name,
        zones=list(payload.zones),
        color=payload.color,
    )
    return RouteResponse.model_validate(route, from_attributes=True)


@router.get("/routes", response_model=list[RouteResponse], dependencies=[_READ])
async def list_routes(
    branch_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> list[RouteResponse]:
    routes = await service.list_routes(tenant_id, branch_id)
    return [RouteResponse.model_validate(r, from_attributes=True) for r in routes]


@router.patch(
    "/routes/{route_id}", response_model=RouteResponse, dependencies=[_MANAGE]
)
async def update_route(
    route_id: uuid.UUID,
    payload: UpdateRouteRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> RouteResponse:
    route = await service.update_route(
        tenant_id, route_id, payload.model_dump(exclude_unset=True)
    )
    return RouteResponse.model_validate(route, from_attributes=True)


# --- Route drivers ----------------------------------------------------------
@router.post(
    "/routes/{route_id}/drivers",
    response_model=RouteDriverResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def attach_route_driver(
    route_id: uuid.UUID,
    payload: AttachRouteDriverRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> RouteDriverResponse:
    mapping, status_ = await service.attach_route_driver(
        tenant_id, route_id, payload.employee_id
    )
    return RouteDriverResponse(
        id=mapping.id,
        delivery_route_id=mapping.delivery_route_id,
        employee_id=mapping.employee_id,
        is_active=mapping.is_active,
        status=status_,
    )


@router.get(
    "/routes/{route_id}/drivers",
    response_model=list[RouteDriverResponse],
    dependencies=[_READ],
)
async def list_route_drivers(
    route_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> list[RouteDriverResponse]:
    drivers = await service.list_route_drivers(tenant_id, route_id)
    return [
        RouteDriverResponse(
            id=driver.id,
            delivery_route_id=driver.delivery_route_id,
            employee_id=driver.employee_id,
            is_active=driver.is_active,
            status=status_,
        )
        for driver, status_ in drivers
    ]


@router.delete(
    "/routes/{route_id}/drivers/{employee_id}",
    status_code=_NO_CONTENT,
    dependencies=[_MANAGE],
)
async def detach_route_driver(
    route_id: uuid.UUID,
    employee_id: uuid.UUID,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.detach_route_driver(tenant_id, route_id, employee_id)
    return Response(status_code=_NO_CONTENT)


# --- Deliveries -------------------------------------------------------------
@router.post(
    "/deliveries",
    response_model=DeliveryResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def create_delivery(
    payload: CreateDeliveryRequest, service: DeliveryServiceDep, tenant_id: TenantDep
) -> DeliveryResponse:
    delivery = await service.create_delivery(
        tenant_id,
        payload.order_id,
        payload.address_text,
        payload.neighborhood,
        payload.latitude,
        payload.longitude,
    )
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


@router.get("/deliveries", response_model=list[DeliveryResponse], dependencies=[_READ])
async def list_deliveries(
    service: DeliveryServiceDep, tenant_id: TenantDep, status_filter: str | None = None
) -> list[DeliveryResponse]:
    deliveries = await service.list_deliveries(tenant_id, status=status_filter)
    return [
        DeliveryResponse.model_validate(d, from_attributes=True) for d in deliveries
    ]


@router.get(
    "/orders/{order_id}/delivery",
    response_model=DeliveryResponse,
    dependencies=[_READ],
)
async def get_delivery_by_order(
    order_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> DeliveryResponse:
    delivery = await service.get_delivery_by_order(tenant_id, order_id)
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


@router.patch(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
    dependencies=[_MANAGE],
)
async def update_delivery_address(
    delivery_id: uuid.UUID,
    payload: UpdateDeliveryAddressRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> DeliveryResponse:
    delivery = await service.update_delivery_address(
        tenant_id, delivery_id, payload.model_dump(exclude_unset=True)
    )
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


@router.post(
    "/deliveries/{delivery_id}/assign",
    response_model=DeliveryResponse,
    dependencies=[_ASSIGN],
)
async def assign_delivery(
    delivery_id: uuid.UUID,
    payload: AssignDeliveryRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> DeliveryResponse:
    delivery = await service.assign_delivery(
        tenant_id, delivery_id, payload.delivery_run_id
    )
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


@router.post(
    "/deliveries/{delivery_id}/mark-delivered",
    response_model=DeliveryResponse,
    dependencies=[_ASSIGN],
)
async def mark_delivered(
    delivery_id: uuid.UUID,
    payload: MarkDeliveredRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> DeliveryResponse:
    delivery = await service.mark_delivered(tenant_id, delivery_id, payload.delivered)
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


# --- Runs -------------------------------------------------------------------
@router.post(
    "/runs", response_model=RunResponse, status_code=201, dependencies=[_MANAGE]
)
async def create_run(
    payload: CreateRunRequest, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.create_run(
        tenant_id, payload.delivery_route_id, payload.employee_id
    )
    return RunResponse.model_validate(run, from_attributes=True)


@router.get("/runs", response_model=list[RunResponse], dependencies=[_READ])
async def list_runs(
    service: DeliveryServiceDep, tenant_id: TenantDep, status_filter: str | None = None
) -> list[RunResponse]:
    runs = await service.list_runs(tenant_id, status=status_filter)
    return [RunResponse.model_validate(r, from_attributes=True) for r in runs]


@router.get("/runs/{run_id}", response_model=RunResponse, dependencies=[_READ])
async def get_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.get_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.post(
    "/runs/{run_id}/depart", response_model=RunResponse, dependencies=[_ASSIGN]
)
async def depart_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.depart_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.post(
    "/runs/{run_id}/finish", response_model=RunResponse, dependencies=[_ASSIGN]
)
async def finish_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.finish_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)
