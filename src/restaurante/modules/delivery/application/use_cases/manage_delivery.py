"""Application service for the Delivery module (own fleet).

Owns routes, route drivers, per-order delivery records, dispatch runs, and the
explicit lifecycle: assign → depart → deliver → finish. Two forward-only state
machines (delivery and run) with guarded transitions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from restaurante.modules.delivery.application.use_cases.quote_pending import (
    PAYMENT_REQUEST_TTL_HOURS,
)
from restaurante.modules.delivery.domain.entities import (
    DELIVERY_ASSIGNED,
    DELIVERY_CANCELLED,
    DELIVERY_DELIVERED,
    DELIVERY_IN_TRANSIT,
    DELIVERY_NOT_DELIVERED,
    DELIVERY_PENDING,
    DELIVERY_TERMINAL_STATUSES,
    DELIVERY_UNRESOLVED_STATUSES,
    ActiveRunTrail,
    DeliveryPaymentRequest,
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    DeliveryTariffBand,
    OrderDelivery,
    OrderSummary,
    PaymentRequestView,
    RunPosition,
)
from restaurante.modules.delivery.domain.ports import (
    DeliveryRepository,
    GeocodeQueue,
    OrderSettlement,
)
from restaurante.modules.delivery.infrastructure.payment_requests import (
    issue_payment_token,
)
from restaurante.shared.config import get_settings
from restaurante.shared.customer_channel.ports import (
    CUSTOMER_STATE_ASSIGNED,
    CUSTOMER_STATE_DELIVERED,
    CUSTOMER_STATE_ON_THE_WAY,
    EMISSION_NO_CONTACT,
    EMISSION_PENDING,
    CustomerNotifier,
    DeliveryPaymentRequestNotifier,
)
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from restaurante.shared.geo.simplify import douglas_peucker_indices
from restaurante.shared.links import delivery_payment_url
from restaurante.shared.realtime.ports import EventPublisher

# Live-board topic for the Domicilios surface (dispatch board, coverage map, driver view).
EVENT_TOPIC = "delivery"
# Dedicated FAT-event topic for driver positions. Kept OFF `EVENT_TOPIC` on purpose: that one
# is a thin doorbell whose subscribers refetch on every frame, so high-frequency GPS samples
# would trigger a full deliveries refetch each time. Position payloads are applied directly.
POSITION_TOPIC = "driver_position"
# Douglas–Peucker tolerance for the dispatcher trail, in raw lat/lng degrees. ~1e-4° ≈ 11 m —
# below the client's distance throttle, so real bends survive while collinear runs collapse.
POSITION_EPSILON = 0.0001

_log = logging.getLogger(__name__)

# Delivery states. Los nombres cortos son de este módulo; los valores y, sobre todo, QUÉ cuenta
# como resuelto viven en el dominio, porque la caja y los reportes preguntan lo mismo.
D_PENDING = DELIVERY_PENDING
D_ASSIGNED = DELIVERY_ASSIGNED
D_IN_TRANSIT = DELIVERY_IN_TRANSIT
D_DELIVERED = DELIVERY_DELIVERED
D_NOT_DELIVERED = DELIVERY_NOT_DELIVERED
D_CANCELLED = DELIVERY_CANCELLED
# Terminal: a resolved delivery. Cada desenlace llega por su camino —entregada y no entregada
# liquidan la comanda, cancelada la suelta con ella— y los tres liberan la sesión de caja.
D_TERMINAL = DELIVERY_TERMINAL_STATUSES
# Non-terminal: still owes an outcome. These are what block a cash session from closing.
D_UNRESOLVED = DELIVERY_UNRESOLVED_STATUSES

# Mirrors `kitchen.KITCHEN_STATE_READY`. Duplicated as a literal rather than imported so the
# delivery module keeps no compile-time dependency on the kitchen module.
KITCHEN_READY = "ready"

# Run states
R_PREPARING = "preparing"
R_IN_TRANSIT = "in_transit"
R_FINISHED = "finished"

# Fixed list of reasons a driver can give for a failed delivery (free text goes in `comment`).
NOT_DELIVERED_REASONS: frozenset[str] = frozenset(
    {
        "Cliente no contesta",
        "Dirección incorrecta / no la encuentra",
        "Cliente rechazó el pedido",
        "Cliente canceló",
        "Otro",
    }
)


def _compose_not_delivered_reason(reason: str | None, comment: str | None) -> str | None:
    """Join the fixed reason and optional free-text comment into one stored string.

    Stored as ``"reason — comment"`` when both are present, the reason alone when only it is
    given, the comment alone when only it is, and ``None`` when neither is.
    """
    reason = reason.strip() if reason else None
    comment = comment.strip() if comment else None
    if reason and comment:
        return f"{reason} — {comment}"
    return reason or comment


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
            raise ValidationError(f"Cada zona debe tener como máximo {MAX_ZONE_LENGTH} caracteres.")
    return cleaned


def _simplify_trail(trail: list[RunPosition]) -> list[RunPosition]:
    """Douglas–Peucker over a trail's lat/lng, keeping the original points (and endpoints)."""
    if len(trail) <= 2:
        return trail
    coords = [(float(p.latitude), float(p.longitude)) for p in trail]
    kept = douglas_peucker_indices(coords, POSITION_EPSILON)
    return [trail[i] for i in kept]


class DeliveryService:
    def __init__(
        self,
        repo: DeliveryRepository,
        geocode_queue: GeocodeQueue | None = None,
        events: EventPublisher | None = None,
        settlement: OrderSettlement | None = None,
        customer_notifier: CustomerNotifier | None = None,
        payment_notifier: DeliveryPaymentRequestNotifier | None = None,
    ) -> None:
        self._repo = repo
        # Outbound port hacia orders: resolver una entrega cierra su comanda. NO es
        # best-effort — si el cobro en efectivo falla, la entrega tampoco se marca.
        self._settlement = settlement
        # Optional on purpose: with no queue the service behaves exactly as it did before —
        # records still land in the resolver's set and the periodic pass still pins them. The
        # queue only buys latency, so its absence is a slower pin, never a missing one.
        self._geocode_queue = geocode_queue
        # Optional live-board publisher (best-effort doorbell). Absent → today's behaviour
        # exactly; a broker outage never fails a delivery mutation.
        self._events = events
        # Puerto opcional hacia el canal del cliente (WhatsApp). Ausente → nadie recibe nada.
        self._customer_notifier = customer_notifier
        # El mismo canal, para el enlace de pago. Separado del de arriba porque este SÍ informa
        # si salió: quien reemite tiene en la mano un token que sólo existe en memoria.
        self._payment_notifier = payment_notifier

    async def _notify_customer(self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str) -> None:
        """Aviso al cliente. El puerto promete no levantar; aquí se traga igual: un
        domiciliario que sale no puede quedarse dentro porque WhatsApp esté caído."""
        if self._customer_notifier is None:
            return
        try:
            await self._customer_notifier.notify_order_state(tenant_id, order_id, state)
        except Exception:  # noqa: BLE001 - avisar al cliente es un efecto secundario
            pass

    async def _publish(self, tenant_id: uuid.UUID, branch_id: uuid.UUID, kind: str) -> None:
        """Best-effort branch-scoped notification that Domicilios changed.

        A thin doorbell: the client refetches deliveries/runs on receipt. A publish failure
        must never fail the mutation, so it is swallowed here on top of the port's own
        best-effort contract (mirrors the KDS `_publish_event`)."""
        if self._events is None:
            return
        try:
            await self._events.publish(
                EVENT_TOPIC,
                tenant_id,
                branch_id,
                {"kind": kind, "branch_id": str(branch_id)},
            )
        except Exception:  # noqa: BLE001 - board push is a non-blocking side effect
            pass

    async def _publish_position(
        self, tenant_id: uuid.UUID, run: DeliveryRun, position: RunPosition
    ) -> None:
        """Best-effort FAT push of a driver's fix on the dedicated `driver_position` topic.

        The payload carries the position so the dispatcher applies it straight to the marker —
        no refetch. JSON-safe: Decimals as strings, the timestamp as ISO-8601. A broker failure
        must never fail the position write, so it is swallowed here."""
        if self._events is None:
            return
        try:
            await self._events.publish(
                POSITION_TOPIC,
                tenant_id,
                run.branch_id,
                {
                    "run_id": str(run.id),
                    "employee_id": str(run.employee_id),
                    "latitude": str(position.latitude),
                    "longitude": str(position.longitude),
                    "recorded_at": (
                        position.recorded_at.isoformat()
                        if position.recorded_at is not None
                        else None
                    ),
                    "branch_id": str(run.branch_id),
                },
            )
        except Exception:  # noqa: BLE001 - position push is a non-blocking side effect
            pass

    async def _publish_run_removed(self, tenant_id: uuid.UUID, run: DeliveryRun) -> None:
        """Best-effort removal frame on the `driver_position` topic.

        A finished run stops emitting fixes, so the dispatcher's live layer would only drop it
        on the slow (~60s) authoritative reconcile. This tombstone lets the client remove the
        marker + trail immediately: it carries no coordinates, just the run to forget, flagged
        by `event: "finished"`. Same swallow-on-failure contract as `_publish_position`."""
        if self._events is None:
            return
        try:
            await self._events.publish(
                POSITION_TOPIC,
                tenant_id,
                run.branch_id,
                {
                    "event": "finished",
                    "run_id": str(run.id),
                    "branch_id": str(run.branch_id),
                },
            )
        except Exception:  # noqa: BLE001 - removal push is a non-blocking side effect
            pass

    # --- internal guards ---------------------------------------------------
    async def _require_branch(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_route(self, tenant_id: uuid.UUID, route_id: uuid.UUID) -> DeliveryRoute:
        route = await self._repo.get_route(tenant_id, route_id)
        if route is None:
            raise NotFoundError(f"Ruta no encontrada: {route_id}")
        return route

    async def _require_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
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

    async def _announce_quote(self, delivery: OrderDelivery) -> None:
        """Ask the worker to price an already-pinned delivery now. Never raises.

        Same contract as the geocode announcement: the minute-by-minute sweep reads the rows,
        so losing this costs the customer a tick and never a price.
        """
        if self._geocode_queue is None or delivery.id is None:
            return
        announce_quote = getattr(self._geocode_queue, "announce_quote", None)
        if announce_quote is None:
            return
        try:
            await announce_quote(delivery.tenant_id, delivery.id)
        except Exception:  # noqa: BLE001 - the adapter swallows; this is the second belt
            _log.warning(
                "Announcing delivery %s for quoting failed; the sweep will price it.",
                delivery.id,
                exc_info=True,
            )

    async def _announce_if_pending(self, delivery: OrderDelivery) -> None:
        """Announce a record that needs a pin, so it is resolved in seconds.

        Only records actually in the resolver's set are announced: one with a pin is never
        swept, so announcing it would be a lie the worker would have to re-check.

        Never raises, whatever the queue does. The set of work is the predicate over the rows,
        so a lost announcement costs latency; letting it reach the caller would cost the order.
        """
        if self._geocode_queue is None or delivery.id is None:
            return
        if delivery.latitude is not None or delivery.longitude is not None:
            # It already has a pin, so the geocoder will never touch it — but the quoter is
            # waiting on exactly those coordinates, and they are here now. Without this, a GPS
            # order pays a full sweep tick for a calculation that takes microseconds.
            await self._announce_quote(delivery)
            return
        if not delivery.address_text.strip():
            return
        try:
            await self._geocode_queue.announce(delivery.tenant_id, delivery.id)
        except Exception:  # noqa: BLE001 - the adapter swallows; this is the second belt
            _log.warning(
                "Announcing delivery %s for geocoding failed; the periodic pass will "
                "resolve it.",
                delivery.id,
                exc_info=True,
            )

    # --- Branch delivery settings -------------------------------------------
    async def get_settings(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> DeliverySetting:
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
        updated = await self._repo.update_settings_by_branch(tenant_id, branch_id, fields)
        assert updated is not None
        return updated

    async def list_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryTariffBand]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_tariff_bands(tenant_id, branch_id)

    async def get_payment_request(
        self, token_hash: str
    ) -> DeliveryPaymentRequest | None:
        """La solicitud viva detrás de un token, o None si no existe, ya se usó o venció."""
        request = await self._repo.get_payment_request_by_token(token_hash)
        if (
            request is None
            or request.status != "pending"
            or request.expires_at <= datetime.now(UTC)
        ):
            return None
        return request

    async def payment_request_view(self, token_hash: str) -> PaymentRequestView | None:
        """La página completa para un token vivo: pedido, líneas, domicilio y saldo."""
        request = await self.get_payment_request(token_hash)
        if request is None:
            return None
        return await self._repo.payment_request_view(request)

    async def select_payment_method(
        self, token_hash: str, method: str
    ) -> DeliveryPaymentRequest:
        request = await self.get_payment_request(token_hash)
        if request is None:
            raise NotFoundError("Solicitud de pago no encontrada o vencida.")
        await self._repo.set_payment_method_for_request(request, method)
        return request

    async def reissue_payment_request(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> DeliveryPaymentRequest:
        """Emitir DE NUEVO el enlace de pago de una entrega ya cotizada.

        No es un reenvío, y no puede serlo: de la solicitud anterior sólo se guardó el hash del
        token, así que su enlace no existe en ninguna parte. Esto acuña una solicitud NUEVA
        sobre la MISMA cotización congelada —no recalcula nada, el cliente ve el mismo total—
        invalida la anterior y la manda.

        Para cuando el envío falló, el cliente borró el chat, o el pedido se vinculó a WhatsApp
        después de cotizarse.
        """
        delivery = await self._require_delivery(tenant_id, delivery_id)
        if delivery.quote_status != "quoted" or delivery.quoted_fee is None:
            raise ValidationError("Sólo se puede reenviar el enlace de una entrega ya cotizada.")
        if delivery.id is None:  # pragma: no cover - loaded rows always have one
            raise NotFoundError(f"Entrega no encontrada: {delivery_id}")

        await self._repo.invalidate_payment_requests_for_delivery(tenant_id, delivery.id)
        raw_token, token_hash = issue_payment_token()
        request = await self._repo.create_payment_request(
            DeliveryPaymentRequest(
                tenant_id=tenant_id,
                branch_id=delivery.branch_id,
                order_id=delivery.order_id,
                order_delivery_id=delivery.id,
                token_hash=token_hash,
                # The frozen quote, copied verbatim. Re-issuing a link must never become a
                # back door for re-pricing an order the customer already agreed to.
                quote_distance_km=delivery.quote_distance_km or Decimal("0"),
                quoted_fee=delivery.quoted_fee,
                expires_at=datetime.now(UTC) + timedelta(hours=PAYMENT_REQUEST_TTL_HOURS),
                raw_token=raw_token,
            )
        )
        await self._emit_payment_request(request, raw_token, delivery.quoted_fee)
        return request

    async def _emit_payment_request(
        self,
        request: DeliveryPaymentRequest,
        raw_token: str,
        fee: Decimal,
    ) -> None:
        """Hand the freshly minted link to the customer and record what happened.

        Mirrors the quoting worker's emission because it has the same constraint: this is the
        only moment `raw_token` is readable.
        """
        if request.id is None:  # pragma: no cover - the repository always assigns one
            return
        if self._payment_notifier is None:
            await self._repo.record_payment_request_emission(
                request.tenant_id,
                request.id,
                emission_status=EMISSION_PENDING,
                reason="La mensajería no está configurada.",
            )
            return
        slug = await self._repo.tenant_slug(request.tenant_id)
        url = delivery_payment_url(get_settings().storefront_base_url, slug, raw_token)
        if not url:
            await self._repo.record_payment_request_emission(
                request.tenant_id,
                request.id,
                emission_status=EMISSION_NO_CONTACT,
                reason="Falta configurar la URL pública de la carta (STOREFRONT_BASE_URL).",
            )
            return
        outcome = await self._payment_notifier.notify_delivery_payment_request(
            request.tenant_id,
            request.order_id,
            request_id=request.id,
            payment_url=url,
            delivery_fee=fee,
        )
        await self._repo.record_payment_request_emission(
            request.tenant_id,
            request.id,
            emission_status=outcome.status,
            reason=outcome.reason,
            emitted_at=datetime.now(UTC) if outcome.sent else None,
        )

    async def replace_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, bands: list[dict[str, Any]]
    ) -> list[DeliveryTariffBand]:
        await self._require_branch(tenant_id, branch_id)
        if not bands:
            raise ValidationError("Debe configurar al menos una tarifa de domicilio.")
        maxima = [Decimal(str(b["max_distance_km"])) for b in bands]
        fees = [Decimal(str(b["fee"])) for b in bands]
        if (
            any(distance <= 0 for distance in maxima)
            or any(fee < 0 for fee in fees)
            or maxima != sorted(set(maxima))
        ):
            raise ValidationError(
                "Las distancias deben ser positivas, crecientes y sin duplicados; "
                "la tarifa no puede ser negativa."
            )
        return await self._repo.replace_tariff_bands(
            tenant_id,
            branch_id,
            [
                DeliveryTariffBand(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    max_distance_km=distance,
                    fee=fee,
                    position=index,
                )
                for index, (distance, fee) in enumerate(zip(maxima, fees, strict=True))
            ],
        )

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

    async def list_routes(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> list[DeliveryRoute]:
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
        route = await self._require_route(tenant_id, route_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        if await self._repo.route_driver_exists(tenant_id, route_id, employee_id):
            raise ConflictError("El repartidor ya está asignado a esa ruta.")
        mapping = await self._repo.create_route_driver(
            DeliveryRouteDriver(
                tenant_id=tenant_id,
                # Derived from the route, never taken from the request.
                branch_id=route.branch_id,
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
        # The order's branch IS the delivery's branch — a pending delivery has no route to
        # take it from. One lookup proves the order exists and yields its branch.
        branch_id = await self._repo.order_branch(tenant_id, order_id)
        if branch_id is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        if await self._repo.get_delivery_by_order(tenant_id, order_id) is not None:
            raise ConflictError("La orden ya tiene un registro de entrega.")
        # No geocoding here, deliberately: taking an order never waits on a provider. A pin-less
        # record with an address is the resolver's set, and it is pinned moments later. An
        # explicit pin from the map picker is stored as given and never swept.
        delivery = await self._repo.create_delivery(
            OrderDelivery(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order_id,
                address_text=address_text,
                neighborhood=neighborhood,
                latitude=latitude,
                longitude=longitude,
            )
        )
        # The record is already in the resolver's set at this point; this only asks for it to
        # be taken now rather than at the next pass. It cannot fail the create.
        await self._announce_if_pending(delivery)
        await self._publish(tenant_id, branch_id, "created")
        return delivery

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery:
        delivery = await self._repo.get_delivery_by_order(tenant_id, order_id)
        if delivery is None:
            raise NotFoundError(f"Entrega no encontrada para la orden: {order_id}")
        return delivery

    async def release_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool:
        """Suelta la entrega de una comanda que deja de existir. Devuelve si soltó algo.

        Se llama al cancelar (y al cerrar por un camino que no resuelve la entrega). Es la misma
        obligación que liberar la mesa: la comanda se acaba y hay que soltar lo que tenía cogido.

        Sólo toca la entrega que sigue en `pending` — la que nunca salió. Una `assigned` o
        `in_transit` va con alguien que tiene la comida en la mano, y cancelarla en silencio le
        borraría la parada del móvil sin decirle por qué; ese desenlace sigue siendo suyo,
        marcándola no entregada con su motivo.

        No liquida nada: la comanda que dispara esto ya está decidiendo su propio dinero. Y no
        levanta por no encontrar entrega — la mayoría de las comandas no son domicilios.
        """
        delivery = await self._repo.get_delivery_by_order(tenant_id, order_id)
        if delivery is None or delivery.id is None:
            return False
        if delivery.delivery_status != D_PENDING:
            return False
        await self._repo.update_delivery(
            tenant_id,
            delivery.id,
            {"delivery_status": D_CANCELLED, "delivered_at": datetime.now(UTC)},
        )
        await self._publish(tenant_id, delivery.branch_id, "cancelled")
        return True

    async def list_deliveries(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
        open_session_only: bool = False,
    ) -> list[OrderDelivery]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_deliveries(
            tenant_id, branch_id, status=status, open_session_only=open_session_only
        )

    async def payment_emissions_for(
        self, tenant_id: uuid.UUID, delivery_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str | None]]:
        """Estado de emisión del enlace de pago por entrega, en una sola lectura."""
        return await self._repo.payment_emissions_for_deliveries(tenant_id, delivery_ids)

    async def update_delivery_address(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery:
        await self._require_delivery(tenant_id, delivery_id)
        # A new address makes the old pin wrong. Clearing it puts the record back into the
        # sweeper's "needs a pin" set, which preserves the old "editing an address re-geocodes"
        # behaviour — just asynchronously, and without making the operator wait for it.
        # An explicit pin in the same patch is the operator placing it by hand: it wins, and
        # the record never re-enters the set.
        address_changed = "address_text" in fields
        location_changed = address_changed or "latitude" in fields or "longitude" in fields
        if address_changed and fields.get("latitude") is None and fields.get("longitude") is None:
            fields = {**fields, "latitude": None, "longitude": None}
        if location_changed:
            fields = {
                **fields,
                "quote_status": "pending_quote",
                "quote_raw_distance_km": None,
                "quote_buffer_km": None,
                "quote_distance_km": None,
                "quote_method": None,
                "quoted_fee": None,
                "quoted_at": None,
                "quote_failure_reason": None,
            }
            updated = await self._repo.apply_quote(tenant_id, delivery_id, fields)
            # El enlace de pago cotizaba la dirección ANTERIOR. Dejarlo vivo permite que el
            # cliente pague un domicilio que ya no existe —normalmente el barato, porque la
            # corrección suele alejar el punto— y que el negocio descubra la diferencia en la
            # puerta. Muere aquí, en la misma corrección que borra la tarifa.
            await self._repo.invalidate_payment_requests_for_delivery(tenant_id, delivery_id)
        else:
            updated = await self._repo.update_delivery(tenant_id, delivery_id, fields)
        if updated is None:
            raise NotFoundError(f"Entrega no encontrada: {delivery_id}")
        # Only a new address puts the row back into the set, so only that is announced. A
        # patch that leaves the address alone changes nothing about what needs a pin — a
        # pin-less record it touches was already in the set and already announced when the
        # address was written. `_announce_if_pending` reads the stored record, so a surviving
        # explicit pin is filtered out there rather than guessed at from the patch.
        if address_changed:
            await self._announce_if_pending(updated)
        return updated

    # --- Runs --------------------------------------------------------------
    async def create_run(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun:
        route = await self._require_route(tenant_id, route_id)
        if not await self._repo.is_active_driver_on_route(tenant_id, route_id, employee_id):
            raise ValidationError("El empleado no es un repartidor activo de esa ruta.")
        return await self._repo.create_run(
            DeliveryRun(
                tenant_id=tenant_id,
                # Derived from the route, never taken from the request.
                branch_id=route.branch_id,
                delivery_route_id=route_id,
                employee_id=employee_id,
            )
        )

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        return await self._require_run(tenant_id, run_id)

    async def list_runs(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_runs(tenant_id, branch_id, status=status)

    # --- Lifecycle ---------------------------------------------------------
    async def assign_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, run_id: uuid.UUID
    ) -> OrderDelivery:
        delivery = await self._require_delivery(tenant_id, delivery_id)
        run = await self._require_run(tenant_id, run_id)
        # A branch's driver cannot carry another branch's order. Only checkable since the
        # records carry a branch; before that this silently produced cross-branch data.
        if delivery.branch_id != run.branch_id:
            raise ConflictError("La entrega y el despacho son de sucursales distintas.")
        if run.status != R_PREPARING:
            raise ConflictError(f"El despacho no está en preparación (estado: {run.status}).")
        if delivery.delivery_status not in (D_PENDING, D_ASSIGNED):
            raise ConflictError(
                f"La entrega no se puede asignar (estado: {delivery.delivery_status})."
            )
        # No se despacha lo que la cocina no ha terminado. La regla es la misma para efectivo y
        # para prepago: el método de pago decide cuándo entra la plata, nunca cuándo sale la
        # comida. Se lee del pedido en cada intento — la entrega no guarda copia de este hecho.
        kitchen_state = await self._repo.order_kitchen_state(tenant_id, delivery.order_id)
        if kitchen_state != KITCHEN_READY:
            raise ConflictError(
                "El pedido todavía no está listo en cocina; no se puede asignar a un despacho."
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
        await self._publish(tenant_id, updated.branch_id, "status")
        await self._notify_customer(tenant_id, updated.order_id, CUSTOMER_STATE_ASSIGNED)
        return updated

    async def depart_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        run = await self._require_run(tenant_id, run_id)
        if run.status != R_PREPARING:
            raise ConflictError(f"El despacho no está en preparación (estado: {run.status}).")
        # Se leen ANTES de despachar: al salir, sus estados ya son `in_transit` y quedaría
        # sin saber a qué pedidos avisar.
        departing = await self._repo.list_deliveries_for_run(tenant_id, run_id)
        await self._repo.mark_run_deliveries_in_transit(tenant_id, run_id)
        updated = await self._repo.update_run(
            tenant_id,
            run_id,
            {"status": R_IN_TRANSIT, "departed_at": datetime.now(UTC)},
        )
        assert updated is not None
        await self._publish(tenant_id, updated.branch_id, "status")
        # "Va en camino" es del PEDIDO, no del despacho: un despacho lleva varios y cada
        # cliente sólo sabe del suyo.
        for delivery in departing:
            await self._notify_customer(tenant_id, delivery.order_id, CUSTOMER_STATE_ON_THE_WAY)
        return updated

    async def mark_delivered(
        self,
        tenant_id: uuid.UUID,
        delivery_id: uuid.UUID,
        delivered: bool,
        *,
        reason: str | None = None,
        comment: str | None = None,
        collected_by_employee_id: uuid.UUID | None = None,
    ) -> OrderDelivery:
        delivery = await self._require_delivery(tenant_id, delivery_id)
        if delivery.delivery_status in D_TERMINAL:
            raise ConflictError(
                f"La entrega ya está resuelta (estado: {delivery.delivery_status})."
            )
        if delivered and delivery.delivery_status != D_IN_TRANSIT:
            # Entregar exige haber salido. Lo contrario permitiría cerrar como entregado algo
            # que sigue en el mostrador.
            raise ConflictError(
                "La entrega debe estar en camino para marcarla entregada "
                f"(estado: {delivery.delivery_status})."
            )
        # "No entregada" se acepta desde cualquier estado no terminal, incluido un pedido que se
        # cocinó y nunca salió. Sin esta salida, una entrega así sería inmortal y dejaría la caja
        # de su turno bloqueada para siempre.
        # The reason belongs to a failure only. A successful delivery ignores it (and clears
        # any value), so a `delivered=True` call never records a not-delivered reason.
        if delivered:
            stored_reason: str | None = None
        else:
            if reason is not None and reason not in NOT_DELIVERED_REASONS:
                raise ValidationError(f"Motivo de no entrega inválido: {reason}")
            stored_reason = _compose_not_delivered_reason(reason, comment)
        new_status = D_DELIVERED if delivered else D_NOT_DELIVERED
        # Se liquida ANTES de marcar la entrega. Si el cobro en efectivo falla, la entrega no
        # queda marcada: un domiciliario no puede creer que cerró algo que no cobró.
        collector = collected_by_employee_id or await self._collector_of(tenant_id, delivery)
        await self._settle(tenant_id, delivery.order_id, delivered, collector)
        updated = await self._repo.update_delivery(
            tenant_id,
            delivery_id,
            {
                "delivery_status": new_status,
                "delivered_at": datetime.now(UTC),
                "not_delivered_reason": stored_reason,
            },
        )
        assert updated is not None
        await self._publish(tenant_id, updated.branch_id, "status")
        if delivered:
            # Sólo el desenlace bueno habla. Un "no entregado" es una conversación que
            # tiene que tener una persona, no una plantilla.
            await self._notify_customer(tenant_id, updated.order_id, CUSTOMER_STATE_DELIVERED)
        return updated

    async def _settle(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        delivered: bool,
        collected_by_employee_id: uuid.UUID | None,
    ) -> None:
        """Cierra la comanda detrás de la entrega. Los dos desenlaces la cierran.

        Deliberadamente NO se traga los errores: si esto falla, la entrega no se marca. Es lo
        contrario del doorbell — aquí hay dinero e inventario de por medio.
        """
        if self._settlement is None:
            return
        if delivered:
            await self._settlement.settle_delivered(tenant_id, order_id, collected_by_employee_id)
        else:
            await self._settlement.settle_not_delivered(tenant_id, order_id)

    async def _collector_of(
        self, tenant_id: uuid.UUID, delivery: OrderDelivery
    ) -> uuid.UUID | None:
        """Quién recogió el dinero: el domiciliario del despacho.

        Cuando un despachador marca la entrega en nombre del domiciliario —porque se quedó sin
        batería, o ya volvió— la plata la recibió igualmente el domiciliario. Atribuirla al
        despachador diría que el dinero pasó por unas manos por las que no pasó.
        """
        if delivery.delivery_run_id is None:
            return None
        run = await self._repo.get_run(tenant_id, delivery.delivery_run_id)
        return run.employee_id if run else None

    async def finish_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun:
        run = await self._require_run(tenant_id, run_id)
        if run.status != R_IN_TRANSIT:
            raise ConflictError(f"El despacho no está en camino (estado: {run.status}).")
        updated = await self._repo.update_run(
            tenant_id,
            run_id,
            {"status": R_FINISHED, "finished_at": datetime.now(UTC)},
        )
        assert updated is not None
        # The trail is operational, tied to the active run: prune it so the finished driver
        # leaves the dispatcher's live layer and the table does not accrete history.
        await self._repo.delete_run_positions(tenant_id, run_id)
        await self._publish(tenant_id, updated.branch_id, "status")
        # Tombstone on the driver_position topic so the dispatcher drops the marker + trail
        # immediately, instead of lingering until the slow reconcile re-reads the active set.
        await self._publish_run_removed(tenant_id, updated)
        return updated

    # --- Driver self-service ------------------------------------------------
    # A driver acts only on their OWN run (ownership = run.employee_id == the driver),
    # authorized by `delivery.drive` at the API edge. These methods take the caller's
    # resolved `employee_id`/`branch_id` (never client-supplied) and reuse the same state
    # machine as the dispatcher path.
    async def _require_own_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun:
        run = await self._require_run(tenant_id, run_id)
        if run.employee_id != employee_id:
            # 404, not 403: another driver's run must not even be observable here.
            raise NotFoundError(f"Despacho no encontrado: {run_id}")
        return run

    async def _enrich_run(
        self, tenant_id: uuid.UUID, run: DeliveryRun
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]]:
        assert run.id is not None
        deliveries = await self._repo.list_deliveries_for_run(tenant_id, run.id)
        order_ids = [d.order_id for d in deliveries]
        summaries = await self._repo.order_summaries(tenant_id, order_ids) if order_ids else {}
        return run, [(d, summaries.get(d.order_id)) for d in deliveries]

    async def open_my_run(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        route_id: uuid.UUID | None = None,
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]]:
        """Self-open a despacho: one active run at a time, then pull the branch's pending
        (unassigned) deliveries onto it — zone-agnostic, reusing the assign guards."""
        # One active run at a time: opening while one exists returns it (idempotent).
        existing = await self._repo.active_run_for_employee(tenant_id, employee_id)
        if existing is not None:
            return await self._enrich_run(tenant_id, existing)

        # The run needs a route (its vehicle). Resolve the driver's active routes in their
        # branch: exactly one is used, several require a choice, none is rejected.
        routes = [
            r
            for r in await self._repo.active_routes_for_driver(tenant_id, employee_id)
            if r.branch_id == branch_id
        ]
        if not routes:
            raise ValidationError("No tienes una ruta asignada para abrir un despacho.")
        if route_id is not None:
            route = next((r for r in routes if r.id == route_id), None)
            if route is None:
                raise ValidationError("La ruta elegida no es una de tus rutas activas.")
        elif len(routes) == 1:
            route = routes[0]
        else:
            raise ValidationError("Conduces varias rutas: elige la ruta del despacho.")
        assert route.id is not None

        run = await self.create_run(tenant_id, route.id, employee_id)
        assert run.id is not None
        # Pull the branch's pending, unassigned deliveries — regardless of zone/route.
        pending = await self._repo.list_deliveries(tenant_id, branch_id, status=D_PENDING)
        for delivery in pending:
            if delivery.delivery_run_id is None and delivery.id is not None:
                await self.assign_delivery(tenant_id, delivery.id, run.id)
        await self._publish(tenant_id, branch_id, "status")
        return await self._enrich_run(tenant_id, run)

    async def list_my_routes(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryRoute]:
        """The routes the driver actively drives in their branch — the choices for opening a
        run (mirrors the resolution in `open_my_run`)."""
        return [
            r
            for r in await self._repo.active_routes_for_driver(tenant_id, employee_id)
            if r.branch_id == branch_id
        ]

    async def get_my_run(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]] | None:
        run = await self._repo.active_run_for_employee(tenant_id, employee_id)
        if run is None:
            return None
        return await self._enrich_run(tenant_id, run)

    async def depart_my_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, employee_id: uuid.UUID
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]]:
        await self._require_own_run(tenant_id, run_id, employee_id)
        run = await self.depart_run(tenant_id, run_id)
        return await self._enrich_run(tenant_id, run)

    async def finish_my_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun:
        await self._require_own_run(tenant_id, run_id, employee_id)
        return await self.finish_run(tenant_id, run_id)

    # --- Live positions -----------------------------------------------------
    async def record_my_position(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        latitude: Decimal,
        longitude: Decimal,
    ) -> RunPosition:
        """Append a fix to the caller's OWN active run, then push it (best-effort).

        Ownership is implicit: the run is resolved from the caller, never client-supplied. No
        active run → the driver has nothing to track against, so the push is rejected."""
        run = await self._repo.active_run_for_employee(tenant_id, employee_id)
        if run is None:
            raise ConflictError("No tienes un despacho activo para registrar tu ubicación.")
        assert run.id is not None
        position = await self._repo.append_position(
            tenant_id, run.id, run.branch_id, latitude, longitude
        )
        # Publish AFTER the write and best-effort — a broker outage never loses the fix.
        await self._publish_position(tenant_id, run, position)
        return position

    async def list_active_positions(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[ActiveRunTrail]:
        """Each active run's driver trail for the dispatcher, Douglas–Peucker-simplified.

        Only active runs with at least one fix appear; the last trail point is the current
        position (endpoints are always kept by the simplification)."""
        await self._require_branch(tenant_id, branch_id)
        trails = await self._repo.active_runs_positions(tenant_id, branch_id)
        return [
            ActiveRunTrail(
                run_id=t.run_id,
                employee_id=t.employee_id,
                trail=_simplify_trail(t.trail),
            )
            for t in trails
        ]

    async def _require_own_delivery_run(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, employee_id: uuid.UUID
    ) -> tuple[OrderDelivery, DeliveryRun]:
        delivery = await self._require_delivery(tenant_id, delivery_id)
        if delivery.delivery_run_id is None:
            raise ConflictError("La entrega no está en un despacho.")
        run = await self._require_own_run(tenant_id, delivery.delivery_run_id, employee_id)
        return delivery, run

    async def mark_my_delivered(
        self,
        tenant_id: uuid.UUID,
        delivery_id: uuid.UUID,
        employee_id: uuid.UUID,
        delivered: bool,
        *,
        reason: str | None = None,
        comment: str | None = None,
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]]:
        _, run = await self._require_own_delivery_run(tenant_id, delivery_id, employee_id)
        # El domiciliario es quien cobra en la puerta: el pago en efectivo se le atribuye.
        await self.mark_delivered(
            tenant_id,
            delivery_id,
            delivered,
            reason=reason,
            comment=comment,
            collected_by_employee_id=employee_id,
        )
        return await self._enrich_run(tenant_id, run)

    async def unassign_my_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, employee_id: uuid.UUID
    ) -> tuple[DeliveryRun, list[tuple[OrderDelivery, OrderSummary | None]]]:
        """Return a wrongly-pulled delivery to the pending pool while the run is still
        `preparing`; once departed, the delivery can no longer be removed this way."""
        _, run = await self._require_own_delivery_run(tenant_id, delivery_id, employee_id)
        if run.status != R_PREPARING:
            raise ConflictError("El despacho ya salió; no se puede quitar la entrega.")
        updated = await self._repo.update_delivery(
            tenant_id,
            delivery_id,
            {
                "delivery_run_id": None,
                "delivery_route_id": None,
                "delivery_status": D_PENDING,
            },
        )
        assert updated is not None
        await self._publish(tenant_id, run.branch_id, "status")
        return await self._enrich_run(tenant_id, run)
