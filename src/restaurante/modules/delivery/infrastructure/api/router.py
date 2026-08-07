"""Delivery API: own-fleet routes, drivers, deliveries, runs and lifecycle.

RBAC: reads `delivery.read`; configuration/creation `delivery.manage`; dispatcher-driven
lifecycle (assign, depart, mark delivered, finish) `delivery.assign`. Driver self-service
(`/delivery/me/...`) is gated by `delivery.drive` PLUS run ownership — a driver only ever
acts on their own run.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from restaurante.modules.delivery.domain.entities import (
    DeliveryRun,
    OrderDelivery,
    OrderSummary,
)
from restaurante.modules.delivery.infrastructure.api.deps import (
    CurrentDriverDep,
    DeliveryServiceDep,
    EventStreamDep,
    TenantDep,
)
from restaurante.modules.delivery.infrastructure.api.schemas import (
    ActiveDriverPositionResponse,
    AssignDeliveryRequest,
    AttachRouteDriverRequest,
    CreateDeliveryRequest,
    CreateRouteRequest,
    CreateRunRequest,
    DeclarePaymentRequest,
    DeliveryResponse,
    DeliverySettingsResponse,
    DriverStopResponse,
    MarkDeliveredRequest,
    MyRunResponse,
    OpenMyRunRequest,
    OrderLineResponse,
    PaymentRequestEmissionResponse,
    PaymentRequestResponse,
    PaymentRequestViewResponse,
    ReplaceTariffBandsRequest,
    RouteDriverResponse,
    RouteResponse,
    RunLocationRequest,
    RunPositionResponse,
    RunResponse,
    SelectPaymentMethodRequest,
    TariffBandResponse,
    TrailPointResponse,
    UpdateDeliveryAddressRequest,
    UpdateDeliverySettingsRequest,
    UpdateRouteRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import (
    require_any_permission,
    require_permission,
)
from restaurante.modules.orders.infrastructure.api.deps import PaymentServiceDep
from restaurante.modules.orders.infrastructure.payment_proof import MAX_PROOF_BYTES
from restaurante.modules.storefront.infrastructure.api.deps import ProofStoreDep
from restaurante.shared.realtime.deps import event_stream_response

router = APIRouter(prefix="/delivery", tags=["delivery"])


@router.get("/payment-requests/{token}", response_model=PaymentRequestViewResponse)
async def read_payment_request(
    token: str, service: DeliveryServiceDep
) -> PaymentRequestViewResponse:
    """Todo lo que la página de pago necesita, en una lectura.

    Devuelve el pedido con sus líneas y su dinero, no sólo el cargo de domicilio: al cliente se
    le está pidiendo pagar un total, y un total que no puede desglosar es un total que discute.
    """
    from restaurante.modules.delivery.infrastructure.payment_requests import hash_payment_token

    view = await service.payment_request_view(hash_payment_token(token))
    if view is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Solicitud de pago no encontrada")
    return PaymentRequestViewResponse.model_validate(view, from_attributes=True)


@router.post("/payment-requests/{token}/method", response_model=PaymentRequestResponse)
async def select_payment_method(
    token: str, payload: SelectPaymentMethodRequest, service: DeliveryServiceDep
) -> PaymentRequestResponse:
    from restaurante.modules.delivery.infrastructure.payment_requests import hash_payment_token

    request = await service.select_payment_method(hash_payment_token(token), payload.payment_method)
    return PaymentRequestResponse(
        order_id=request.order_id,
        quote_distance_km=request.quote_distance_km,
        quoted_fee=request.quoted_fee,
        status=request.status,
        expires_at=request.expires_at,
    )


@router.post("/payment-requests/{token}/claim")
async def declare_payment_claim(
    token: str,
    payload: DeclarePaymentRequest,
    service: DeliveryServiceDep,
    payments: PaymentServiceDep,
    tenant_id: TenantDep,
) -> dict[str, Any]:
    from restaurante.modules.delivery.infrastructure.payment_requests import hash_payment_token

    request = await service.get_payment_request(hash_payment_token(token))
    if request is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Solicitud de pago no encontrada o vencida")
    claim = await payments.declare_payment(
        tenant_id, request.order_id, payload.amount, payload.method
    )
    return {"claim_id": claim.id, "status": claim.status, "amount": claim.amount}


@router.post("/payment-requests/{token}/proof")
async def upload_payment_proof(
    token: str,
    amount: Annotated[Decimal, Form()],
    file: Annotated[UploadFile, File()],
    service: DeliveryServiceDep,
    payments: PaymentServiceDep,
    store: ProofStoreDep,
    tenant_id: TenantDep,
) -> dict[str, Any]:
    from restaurante.modules.delivery.infrastructure.payment_requests import hash_payment_token
    from restaurante.shared.domain.errors import ValidationError

    request = await service.get_payment_request(hash_payment_token(token))
    if request is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Solicitud de pago no encontrada o vencida")
    data = await file.read(MAX_PROOF_BYTES + 1)
    if len(data) > MAX_PROOF_BYTES:
        raise ValidationError("El comprobante pesa demasiado (máximo 5 MB).")
    # `store` YA es el guardado con su almacenamiento dentro (`get_proof_store`). Pasárselo a
    # `store_payment_proof` como si fuera el gateway lo envolvía dos veces y reventaba al primer
    # comprobante que un cliente intentara subir desde su enlace de pago.
    proof_url = await store(tenant_id, request.order_id, file.content_type or "", data)
    claim = await payments.declare_payment(
        tenant_id, request.order_id, amount, "transfer", proof_url
    )
    return {"claim_id": claim.id, "status": claim.status, "amount": claim.amount}


_READ = Depends(require_permission("delivery.read"))
_MANAGE = Depends(require_permission("delivery.manage"))
_ASSIGN = Depends(require_permission("delivery.assign"))
_DRIVE = Depends(require_permission("delivery.drive"))


def _stop(delivery: OrderDelivery, summary: OrderSummary | None) -> DriverStopResponse:
    assert delivery.id is not None
    return DriverStopResponse(
        id=delivery.id,
        order_id=delivery.order_id,
        address_text=delivery.address_text,
        neighborhood=delivery.neighborhood,
        latitude=delivery.latitude,
        longitude=delivery.longitude,
        delivery_status=delivery.delivery_status,
        route_position=delivery.route_position,
        notes=delivery.notes,
        not_delivered_reason=delivery.not_delivered_reason,
        delivered_at=delivery.delivered_at,
        order_code=summary.code if summary else None,
        customer_name=summary.customer_name if summary else None,
        customer_phone=summary.customer_phone if summary else None,
        total=summary.total if summary else None,
        payment_method=summary.payment_method if summary else None,
        paid=summary.paid if summary else None,
        items=[
            OrderLineResponse(name=line.name, quantity=line.quantity)
            for line in (summary.items if summary else [])
        ],
    )


def _my_run(
    run: DeliveryRun, stops: list[tuple[OrderDelivery, OrderSummary | None]]
) -> MyRunResponse:
    assert run.id is not None
    return MyRunResponse(
        id=run.id,
        delivery_route_id=run.delivery_route_id,
        employee_id=run.employee_id,
        status=run.status,
        departed_at=run.departed_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        stops=[_stop(d, s) for d, s in stops],
    )


# A delivery record is authored by whoever takes the order (`delivery.address`) and by
# whoever runs dispatch (`delivery.manage`) — the latter kept so roles provisioned before
# the permission split keep working. `delivery.address` deliberately grants nothing else:
# not routes, not drivers, not the branch pin, not runs.
_ADDRESS_WRITE = Depends(require_any_permission("delivery.address", "delivery.manage"))
# Reading one order's delivery: `delivery.read` opens the whole Domicilios surface (board,
# routes, settings) and the frontend nav gates on it, so an order-taker gets this instead.
_ADDRESS_READ = Depends(require_any_permission("delivery.address", "delivery.read"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Live board (SSE) ---------------------------------------------------------
@router.get("/events", dependencies=[_READ])
async def stream_events(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """Server-sent events with the branch's Domicilios changes (heartbeat every ~15 s).

    Deliveries, runs, and pins resolved by the geocoding worker all announce here.
    Degrades to heartbeats-only when the broker is down, so clients keep the connection
    and fall back to polling for data freshness.
    """
    return event_stream_response(stream, "delivery", tenant_id, branch_id)


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


@router.get(
    "/branches/{branch_id}/tariff-bands",
    response_model=list[TariffBandResponse],
    dependencies=[_READ],
)
async def list_tariff_bands(
    branch_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> list[TariffBandResponse]:
    bands = await service.list_tariff_bands(tenant_id, branch_id)
    return [TariffBandResponse.model_validate(band, from_attributes=True) for band in bands]


@router.put(
    "/branches/{branch_id}/tariff-bands",
    response_model=list[TariffBandResponse],
    dependencies=[_MANAGE],
)
async def replace_tariff_bands(
    branch_id: uuid.UUID,
    payload: ReplaceTariffBandsRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> list[TariffBandResponse]:
    bands = await service.replace_tariff_bands(
        tenant_id, branch_id, [band.model_dump() for band in payload.bands]
    )
    return [TariffBandResponse.model_validate(band, from_attributes=True) for band in bands]


@router.post(
    "/deliveries/{delivery_id}/payment-request",
    response_model=PaymentRequestEmissionResponse,
    status_code=201,
    dependencies=[_ASSIGN],
)
async def reissue_payment_request(
    delivery_id: uuid.UUID,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> PaymentRequestEmissionResponse:
    """Reemitir el enlace de pago de una entrega ya cotizada.

    Gated by `delivery.assign` and not `delivery.read`: manda un mensaje al cliente con una
    cifra de dinero, que es la misma autoridad que despachar. NO recotiza — el cliente ve
    exactamente el total que ya se le congeló.

    Es `POST` a un recurso nuevo, no un `PUT` a la solicitud anterior, porque eso es
    literalmente lo que hace: la anterior queda invalidada y nace otra.
    """
    request = await service.reissue_payment_request(tenant_id, delivery_id)
    return PaymentRequestEmissionResponse(
        order_id=request.order_id,
        quoted_fee=request.quoted_fee,
        expires_at=request.expires_at,
        emission_status=request.emission_status,
        emission_failure_reason=request.emission_failure_reason,
    )


# --- Routes -----------------------------------------------------------------
@router.post("/routes", response_model=RouteResponse, status_code=201, dependencies=[_MANAGE])
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


@router.patch("/routes/{route_id}", response_model=RouteResponse, dependencies=[_MANAGE])
async def update_route(
    route_id: uuid.UUID,
    payload: UpdateRouteRequest,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> RouteResponse:
    route = await service.update_route(tenant_id, route_id, payload.model_dump(exclude_unset=True))
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
    mapping, status_ = await service.attach_route_driver(tenant_id, route_id, payload.employee_id)
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
    dependencies=[_ADDRESS_WRITE],
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
    branch_id: uuid.UUID,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
    status_filter: str | None = None,
    open_session_only: bool = False,
) -> list[DeliveryResponse]:
    # `branch_id` is required, like /routes: a tenant-wide list would mix the branches.
    # `open_session_only=true` is the live dispatch board's scope: only the branch's open
    # cash session's deliveries (old/closed-shift ones drop off).
    deliveries = await service.list_deliveries(
        tenant_id, branch_id, status=status_filter, open_session_only=open_session_only
    )
    # Un solo viaje para todas: el tablero lee decenas de entregas a la vez.
    emissions = await service.payment_emissions_for(
        tenant_id, [d.id for d in deliveries if d.id is not None]
    )
    rows: list[DeliveryResponse] = []
    for delivery in deliveries:
        row = DeliveryResponse.model_validate(delivery, from_attributes=True)
        status, reason = emissions.get(delivery.id, (None, None)) if delivery.id else (None, None)
        row.emission_status = status
        row.emission_failure_reason = reason
        rows.append(row)
    return rows


@router.get(
    "/orders/{order_id}/delivery",
    response_model=DeliveryResponse,
    dependencies=[_ADDRESS_READ],
)
async def get_delivery_by_order(
    order_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> DeliveryResponse:
    delivery = await service.get_delivery_by_order(tenant_id, order_id)
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


@router.patch(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
    dependencies=[_ADDRESS_WRITE],
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
    delivery = await service.assign_delivery(tenant_id, delivery_id, payload.delivery_run_id)
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
    delivery = await service.mark_delivered(
        tenant_id,
        delivery_id,
        payload.delivered,
        reason=payload.reason,
        comment=payload.comment,
    )
    return DeliveryResponse.model_validate(delivery, from_attributes=True)


# --- Runs -------------------------------------------------------------------
@router.post("/runs", response_model=RunResponse, status_code=201, dependencies=[_MANAGE])
async def create_run(
    payload: CreateRunRequest, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.create_run(tenant_id, payload.delivery_route_id, payload.employee_id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.get("/runs", response_model=list[RunResponse], dependencies=[_READ])
async def list_runs(
    branch_id: uuid.UUID,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
    status_filter: str | None = None,
) -> list[RunResponse]:
    runs = await service.list_runs(tenant_id, branch_id, status=status_filter)
    return [RunResponse.model_validate(r, from_attributes=True) for r in runs]


@router.get("/runs/{run_id}", response_model=RunResponse, dependencies=[_READ])
async def get_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.get_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.post("/runs/{run_id}/depart", response_model=RunResponse, dependencies=[_ASSIGN])
async def depart_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.depart_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.post("/runs/{run_id}/finish", response_model=RunResponse, dependencies=[_ASSIGN])
async def finish_run(
    run_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> RunResponse:
    run = await service.finish_run(tenant_id, run_id)
    return RunResponse.model_validate(run, from_attributes=True)


# --- Driver self-service (`delivery.drive` + run ownership) ------------------
# Every endpoint below resolves the driver from the session (`CurrentDriverDep`) and acts
# only on that driver's own run. `employee_id`/`branch_id` are never client-supplied.
@router.post("/me/run", response_model=MyRunResponse, dependencies=[_DRIVE])
async def open_my_run(
    payload: OpenMyRunRequest,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> MyRunResponse:
    """Open (self-create + pull) my despacho, or return my already-active run."""
    assert driver.id is not None
    run, stops = await service.open_my_run(
        tenant_id, driver.id, driver.branch_id, route_id=payload.delivery_route_id
    )
    return _my_run(run, stops)


@router.get("/me/run", response_model=MyRunResponse | None, dependencies=[_DRIVE])
async def get_my_run(
    driver: CurrentDriverDep, service: DeliveryServiceDep, tenant_id: TenantDep
) -> MyRunResponse | None:
    """My active run with order-enriched stops, or null when I have none."""
    assert driver.id is not None
    result = await service.get_my_run(tenant_id, driver.id)
    if result is None:
        return None
    run, stops = result
    return _my_run(run, stops)


@router.get("/me/routes", response_model=list[RouteResponse], dependencies=[_DRIVE])
async def list_my_routes(
    driver: CurrentDriverDep, service: DeliveryServiceDep, tenant_id: TenantDep
) -> list[RouteResponse]:
    """The routes I actively drive — the choices when opening a despacho."""
    assert driver.id is not None
    routes = await service.list_my_routes(tenant_id, driver.id, driver.branch_id)
    return [RouteResponse.model_validate(r, from_attributes=True) for r in routes]


@router.post("/me/runs/{run_id}/depart", response_model=MyRunResponse, dependencies=[_DRIVE])
async def depart_my_run(
    run_id: uuid.UUID,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> MyRunResponse:
    assert driver.id is not None
    run, stops = await service.depart_my_run(tenant_id, run_id, driver.id)
    return _my_run(run, stops)


@router.post("/me/runs/{run_id}/finish", response_model=RunResponse, dependencies=[_DRIVE])
async def finish_my_run(
    run_id: uuid.UUID,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> RunResponse:
    assert driver.id is not None
    run = await service.finish_my_run(tenant_id, run_id, driver.id)
    return RunResponse.model_validate(run, from_attributes=True)


@router.post(
    "/me/deliveries/{delivery_id}/mark-delivered",
    response_model=MyRunResponse,
    dependencies=[_DRIVE],
)
async def mark_my_delivered(
    delivery_id: uuid.UUID,
    payload: MarkDeliveredRequest,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> MyRunResponse:
    assert driver.id is not None
    run, stops = await service.mark_my_delivered(
        tenant_id,
        delivery_id,
        driver.id,
        payload.delivered,
        reason=payload.reason,
        comment=payload.comment,
    )
    return _my_run(run, stops)


@router.post(
    "/me/deliveries/{delivery_id}/unassign",
    response_model=MyRunResponse,
    dependencies=[_DRIVE],
)
async def unassign_my_delivery(
    delivery_id: uuid.UUID,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> MyRunResponse:
    """Return a wrongly-pulled delivery to the pool while my run is still `preparing`."""
    assert driver.id is not None
    run, stops = await service.unassign_my_delivery(tenant_id, delivery_id, driver.id)
    return _my_run(run, stops)


@router.post(
    "/me/run/location",
    response_model=RunPositionResponse,
    status_code=201,
    dependencies=[_DRIVE],
)
async def record_my_location(
    payload: RunLocationRequest,
    driver: CurrentDriverDep,
    service: DeliveryServiceDep,
    tenant_id: TenantDep,
) -> RunPositionResponse:
    """Append a GPS fix to my own active run (409 when I have no active run)."""
    assert driver.id is not None
    position = await service.record_my_position(
        tenant_id, driver.id, payload.latitude, payload.longitude
    )
    assert position.recorded_at is not None
    return RunPositionResponse(
        run_id=position.delivery_run_id,
        latitude=position.latitude,
        longitude=position.longitude,
        recorded_at=position.recorded_at,
    )


# --- Live driver positions (dispatcher read + SSE) ---------------------------
@router.get(
    "/positions",
    response_model=list[ActiveDriverPositionResponse],
    dependencies=[_READ],
)
async def list_active_positions(
    branch_id: uuid.UUID, service: DeliveryServiceDep, tenant_id: TenantDep
) -> list[ActiveDriverPositionResponse]:
    """Each active driver's current position + simplified trail for the coverage map."""
    trails = await service.list_active_positions(tenant_id, branch_id)
    result: list[ActiveDriverPositionResponse] = []
    for t in trails:
        current = t.trail[-1]  # non-empty by construction; endpoints are kept
        assert current.recorded_at is not None
        result.append(
            ActiveDriverPositionResponse(
                run_id=t.run_id,
                employee_id=t.employee_id,
                latitude=current.latitude,
                longitude=current.longitude,
                recorded_at=current.recorded_at,
                trail=[
                    TrailPointResponse(
                        latitude=p.latitude,
                        longitude=p.longitude,
                        recorded_at=p.recorded_at,
                    )
                    for p in t.trail
                    if p.recorded_at is not None
                ],
            )
        )
    return result


@router.get("/positions/events", dependencies=[_READ])
async def stream_positions(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """SSE of the dedicated `driver_position` topic — fat position frames, applied directly.

    Separate from `/delivery/events` (the thin CRUD doorbell) so a GPS sample never triggers
    a deliveries refetch. Degrades to heartbeats when the broker is down."""
    return event_stream_response(stream, "driver_position", tenant_id, branch_id)
