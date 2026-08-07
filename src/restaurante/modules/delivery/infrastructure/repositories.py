"""Persistence adapter for the Delivery module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable). Unique-constraint violations are translated
to ``ConflictError``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.delivery.domain.entities import (
    ActiveRunTrail,
    DeliveryPaymentRequest,
    DeliveryRoute,
    DeliveryRouteDriver,
    DeliveryRun,
    DeliverySetting,
    DeliveryTariffBand,
    OrderDelivery,
    OrderLine,
    OrderSummary,
    PaymentRequestLine,
    PaymentRequestView,
    RunPosition,
)
from restaurante.modules.delivery.infrastructure.models import (
    DeliveryPaymentRequestModel,
    DeliveryRouteDriverModel,
    DeliveryRouteModel,
    DeliveryRunModel,
    DeliveryRunPositionModel,
    DeliverySettingModel,
    DeliveryTariffBandModel,
    OrderDeliveryModel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel
from restaurante.modules.menu.infrastructure.models import (
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.domain.order_label import order_label
from restaurante.shared.tenancy.models import BranchModel, TenantModel

_ASSIGNED = "assigned"
_IN_TRANSIT = "in_transit"
_ACTIVE_RUN_STATUSES = ("preparing", "in_transit")
_CANCELLED = "cancelled"


def _order_code(order_id: uuid.UUID) -> str:
    """A short, glanceable label for an order. Delegates to the shared derivation.

    One derivation only: the number the customer reads in their chat has to be the one the
    counter says out loud.
    """
    return order_label(order_id)


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


def _tariff_band(m: DeliveryTariffBandModel) -> DeliveryTariffBand:
    return DeliveryTariffBand(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        max_distance_km=m.max_distance_km,
        fee=m.fee,
        position=m.position,
    )


def _route_driver(m: DeliveryRouteDriverModel) -> DeliveryRouteDriver:
    return DeliveryRouteDriver(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        delivery_route_id=m.delivery_route_id,
        employee_id=m.employee_id,
        is_active=m.is_active,
    )


def _run(m: DeliveryRunModel) -> DeliveryRun:
    return DeliveryRun(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
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
        branch_id=m.branch_id,
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
        not_delivered_reason=m.not_delivered_reason,
        delivered_at=m.delivered_at,
        quote_status=m.quote_status,
        quote_raw_distance_km=m.quote_raw_distance_km,
        quote_buffer_km=m.quote_buffer_km,
        quote_distance_km=m.quote_distance_km,
        quote_method=m.quote_method,
        quoted_fee=m.quoted_fee,
        quoted_at=m.quoted_at,
        quote_failure_reason=m.quote_failure_reason,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _position(m: DeliveryRunPositionModel) -> RunPosition:
    return RunPosition(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        delivery_run_id=m.delivery_run_id,
        latitude=m.latitude,
        longitude=m.longitude,
        recorded_at=m.recorded_at,
    )


def _aware(value: datetime | None) -> datetime | None:
    """Force a stored timestamp to UTC-aware.

    SQLite hands back naive datetimes even from a `timezone=True` column, and the expiry check
    is `expires_at <= now(UTC)` — comparing those two raises `TypeError`, which reads as "this
    link is broken" to a customer who is simply trying to pay.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _payment_request(m: DeliveryPaymentRequestModel) -> DeliveryPaymentRequest:
    """Row → entity. `raw_token` is never set here: the row does not have it, by design."""
    return DeliveryPaymentRequest(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        order_delivery_id=m.order_delivery_id,
        token_hash=m.token_hash,
        quote_distance_km=m.quote_distance_km,
        quoted_fee=m.quoted_fee,
        expires_at=_aware(m.expires_at) or m.expires_at,
        status=m.status,
        created_at=_aware(m.created_at),
        emission_status=m.emission_status,
        emitted_at=_aware(m.emitted_at),
        emission_failure_reason=m.emission_failure_reason,
    )


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_payment_request(
        self, request: DeliveryPaymentRequest
    ) -> DeliveryPaymentRequest:
        model = DeliveryPaymentRequestModel(
            tenant_id=request.tenant_id,
            branch_id=request.branch_id,
            order_id=request.order_id,
            order_delivery_id=request.order_delivery_id,
            token_hash=request.token_hash,
            quote_distance_km=request.quote_distance_km,
            quoted_fee=request.quoted_fee,
            expires_at=request.expires_at,
            status=request.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        # `raw_token` is carried over by hand: it is the caller's, never the row's.
        created = _payment_request(model)
        created.raw_token = request.raw_token
        return created

    async def get_payment_request_by_token(self, token_hash: str) -> DeliveryPaymentRequest | None:
        model = (
            await self._session.execute(
                select(DeliveryPaymentRequestModel).where(
                    DeliveryPaymentRequestModel.token_hash == token_hash,
                )
            )
        ).scalar_one_or_none()
        return None if model is None else _payment_request(model)

    async def record_payment_request_emission(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        emission_status: str,
        reason: str | None = None,
        emitted_at: datetime | None = None,
    ) -> None:
        """Write down whether the customer got the link. Never touches quote, fee or order.

        Separated from `create_payment_request` on purpose: the send happens between the two, and
        a bridge that hangs must not hold a transaction open over the quote it just committed.
        """
        await self._session.execute(
            update(DeliveryPaymentRequestModel)
            .where(
                DeliveryPaymentRequestModel.id == request_id,
                DeliveryPaymentRequestModel.tenant_id == tenant_id,
            )
            .values(
                emission_status=emission_status,
                emission_failure_reason=reason,
                emitted_at=emitted_at,
            )
        )
        await self._session.commit()

    async def invalidate_payment_requests_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> int:
        """Kill every still-usable request for a delivery. Returns how many died.

        Called when the quote it was scoped to stops being true — a re-quote, a corrected
        address — and before issuing a replacement, so two live links never quote two totals.
        """
        result = await self._session.execute(
            update(DeliveryPaymentRequestModel)
            .where(
                DeliveryPaymentRequestModel.order_delivery_id == order_delivery_id,
                DeliveryPaymentRequestModel.tenant_id == tenant_id,
                DeliveryPaymentRequestModel.status == "pending",
            )
            .values(status="invalidated")
        )
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def payment_emissions_for_deliveries(
        self, tenant_id: uuid.UUID, delivery_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str | None]]:
        """Latest payment-request emission per delivery, in ONE query — never one per row.

        Same discipline as `order_summaries`: the dispatch board reads dozens of deliveries at a
        time, and a per-row lookup here is the difference between a board that opens and a board
        that hangs.
        """
        if not delivery_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    DeliveryPaymentRequestModel.order_delivery_id,
                    DeliveryPaymentRequestModel.emission_status,
                    DeliveryPaymentRequestModel.emission_failure_reason,
                    DeliveryPaymentRequestModel.created_at,
                )
                .where(
                    DeliveryPaymentRequestModel.tenant_id == tenant_id,
                    DeliveryPaymentRequestModel.order_delivery_id.in_(delivery_ids),
                )
                .order_by(DeliveryPaymentRequestModel.created_at)
            )
        ).all()
        # Ordered oldest-first and overwritten as we go, so the LAST request wins — which is the
        # one the customer actually holds after a re-issue.
        latest: dict[uuid.UUID, tuple[str, str | None]] = {}
        for delivery_id, status, reason, _created in rows:
            latest[delivery_id] = (status, reason)
        return latest

    async def latest_payment_request_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> DeliveryPaymentRequest | None:
        model = (
            await self._session.execute(
                select(DeliveryPaymentRequestModel)
                .where(
                    DeliveryPaymentRequestModel.order_delivery_id == order_delivery_id,
                    DeliveryPaymentRequestModel.tenant_id == tenant_id,
                )
                .order_by(DeliveryPaymentRequestModel.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if model is None else _payment_request(model)

    async def payment_request_view(
        self, request: DeliveryPaymentRequest
    ) -> PaymentRequestView | None:
        """The whole page in one read: order money, its lines, what is already paid.

        Every figure comes from here and none from the browser. The customer is being shown a
        number to pay; one the page assembled itself is one that can disagree with what the
        restaurant will actually collect.
        """
        order = await self._get_order_model(request.tenant_id, request.order_id)
        if order is None:
            return None

        line_rows = (
            await self._session.execute(
                select(
                    ProductModel.name,
                    ProductVariantModel.name,
                    OrderItemModel.quantity,
                    OrderItemModel.line_subtotal,
                )
                .select_from(OrderItemModel)
                .join(
                    ProductVariantModel,
                    ProductVariantModel.id == OrderItemModel.product_variant_id,
                )
                .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
                .where(
                    OrderItemModel.tenant_id == request.tenant_id,
                    OrderItemModel.order_id == request.order_id,
                    OrderItemModel.status != _CANCELLED,
                )
                .order_by(OrderItemModel.created_at)
            )
        ).all()
        lines = [
            PaymentRequestLine(
                name=name if not variant_name else f"{name} · {variant_name}",
                quantity=quantity,
                line_subtotal=line_subtotal,
            )
            for name, variant_name, quantity, line_subtotal in line_rows
        ]

        paid = (
            await self._session.execute(
                select(func.coalesce(func.sum(OrderPaymentModel.amount), 0)).where(
                    OrderPaymentModel.tenant_id == request.tenant_id,
                    OrderPaymentModel.order_id == request.order_id,
                )
            )
        ).scalar_one()
        # Nunca negativo: un pedido sobre-abonado debe pedir cero, no devolver una cifra en rojo
        # que el cliente lea como "me deben".
        amount_due = max(Decimal("0"), order.total - Decimal(paid))

        delivery = (
            await self._session.execute(
                select(OrderDeliveryModel.address_text).where(
                    OrderDeliveryModel.id == request.order_delivery_id,
                    OrderDeliveryModel.tenant_id == request.tenant_id,
                )
            )
        ).scalar_one_or_none()

        return PaymentRequestView(
            order_id=order.id,
            order_code=_order_code(order.id),
            lines=lines,
            subtotal=order.subtotal,
            discount=order.discount,
            delivery_fee=order.delivery_fee,
            total=order.total,
            amount_due=amount_due,
            quote_distance_km=request.quote_distance_km,
            status=request.status,
            expires_at=request.expires_at,
            address_text=delivery,
            payment_method=order.payment_method,
        )

    async def set_payment_method_for_request(
        self, request: DeliveryPaymentRequest, method: str
    ) -> None:
        await self._session.execute(
            update(OrderModel)
            .where(
                OrderModel.id == request.order_id,
                OrderModel.tenant_id == request.tenant_id,
            )
            .values(payment_method=method)
        )
        await self._session.commit()

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        """The tenant's subdomain. Read with the tenant filter off, on purpose.

        The quote worker runs with no tenant context — it sweeps every tenant's deliveries —
        so the automatic filter would find nothing here and every payment link would come out
        without its subdomain, resolving to no business at all.
        """
        stmt = select(TenantModel.slug).where(TenantModel.id == tenant_id)
        return (
            await self._session.execute(stmt.execution_options(skip_tenant_filter=True))
        ).scalar_one_or_none()

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(self, tenant_id: uuid.UUID, employee_id: uuid.UUID) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def order_branch(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> uuid.UUID | None:
        stmt = select(OrderModel.branch_id).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

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
            existing = await self.get_settings_by_branch(settings.tenant_id, settings.branch_id)
            assert existing is not None
            return existing
        await self._session.refresh(model)
        return _settings(model)

    async def list_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DeliveryTariffBand]:
        stmt = (
            select(DeliveryTariffBandModel)
            .where(
                DeliveryTariffBandModel.tenant_id == tenant_id,
                DeliveryTariffBandModel.branch_id == branch_id,
            )
            .order_by(DeliveryTariffBandModel.position)
        )
        return [_tariff_band(m) for m in (await self._session.execute(stmt)).scalars()]

    async def replace_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, bands: list[DeliveryTariffBand]
    ) -> list[DeliveryTariffBand]:
        await self._session.execute(
            sql_delete(DeliveryTariffBandModel).where(
                DeliveryTariffBandModel.tenant_id == tenant_id,
                DeliveryTariffBandModel.branch_id == branch_id,
            )
        )
        models = [
            DeliveryTariffBandModel(
                tenant_id=band.tenant_id,
                branch_id=band.branch_id,
                max_distance_km=band.max_distance_km,
                fee=band.fee,
                position=band.position,
            )
            for band in bands
        ]
        self._session.add_all(models)
        await self._session.commit()
        for model in models:
            await self._session.refresh(model)
        return [_tariff_band(model) for model in models]

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

    async def next_route_position(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> int:
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

    async def get_route(self, tenant_id: uuid.UUID, route_id: uuid.UUID) -> DeliveryRoute | None:
        model = await self._get_route_model(tenant_id, route_id)
        return _route(model) if model else None

    async def list_routes(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> list[DeliveryRoute]:
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
    async def create_route_driver(self, mapping: DeliveryRouteDriver) -> DeliveryRouteDriver:
        model = DeliveryRouteDriverModel(
            tenant_id=mapping.tenant_id,
            branch_id=mapping.branch_id,
            delivery_route_id=mapping.delivery_route_id,
            employee_id=mapping.employee_id,
            is_active=mapping.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("El repartidor ya está asignado a esa ruta.") from exc
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

    async def active_routes_for_driver(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[DeliveryRoute]:
        stmt = (
            select(DeliveryRouteModel)
            .join(
                DeliveryRouteDriverModel,
                DeliveryRouteDriverModel.delivery_route_id == DeliveryRouteModel.id,
            )
            .where(
                DeliveryRouteDriverModel.tenant_id == tenant_id,
                DeliveryRouteDriverModel.employee_id == employee_id,
                DeliveryRouteDriverModel.is_active.is_(True),
                DeliveryRouteModel.is_active.is_(True),
            )
            .order_by(DeliveryRouteModel.position, DeliveryRouteModel.name)
        )
        return [_route(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_route_drivers(
        self, tenant_id: uuid.UUID, route_id: uuid.UUID
    ) -> list[DeliveryRouteDriver]:
        stmt = select(DeliveryRouteDriverModel).where(
            DeliveryRouteDriverModel.tenant_id == tenant_id,
            DeliveryRouteDriverModel.delivery_route_id == route_id,
        )
        return [_route_driver(m) for m in (await self._session.execute(stmt)).scalars()]

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
            branch_id=delivery.branch_id,
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
            quote_status=delivery.quote_status,
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

    async def _get_order_model(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderModel | None:
        stmt = select(OrderModel).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
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
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
        open_session_only: bool = False,
    ) -> list[OrderDelivery]:
        # The automatic tenancy filter covers tenant_id only — the branch filter is ours.
        stmt = select(OrderDeliveryModel).where(
            OrderDeliveryModel.tenant_id == tenant_id,
            OrderDeliveryModel.branch_id == branch_id,
        )
        if open_session_only:
            # Live board scope: only deliveries whose order belongs to the branch's OPEN cash
            # session. The joins drop null-session (pre-boundary) rows and, with no open session,
            # match nothing — an empty live list.
            stmt = (
                stmt.join(OrderModel, OrderDeliveryModel.order_id == OrderModel.id)
                .join(
                    CashSessionModel,
                    OrderModel.cash_session_id == CashSessionModel.id,
                )
                .where(CashSessionModel.status == "open")
            )
        if status is not None:
            stmt = stmt.where(OrderDeliveryModel.delivery_status == status)
        rows = list((await self._session.execute(stmt)).scalars())
        deliveries = [_delivery(m) for m in rows]
        # One extra query for the whole page, not one per delivery: Dispatch has to paint the
        # "not cooked yet" block on every row.
        states = await self.kitchen_states_for_orders(tenant_id, [d.order_id for d in deliveries])
        for delivery in deliveries:
            delivery.kitchen_state = states.get(delivery.order_id)
        return deliveries

    async def order_kitchen_state(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> str | None:
        """The order's derived kitchen readiness, or None when the order is gone."""
        stmt = select(OrderModel.kitchen_state).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def kitchen_states_for_orders(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not order_ids:
            return {}
        stmt = select(OrderModel.id, OrderModel.kitchen_state).where(
            OrderModel.tenant_id == tenant_id, OrderModel.id.in_(order_ids)
        )
        return {row[0]: row[1] for row in (await self._session.execute(stmt)).all()}

    async def list_deliveries_for_run(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[OrderDelivery]:
        stmt = (
            select(OrderDeliveryModel)
            .where(
                OrderDeliveryModel.tenant_id == tenant_id,
                OrderDeliveryModel.delivery_run_id == run_id,
            )
            .order_by(
                OrderDeliveryModel.route_position.is_(None),
                OrderDeliveryModel.route_position,
                OrderDeliveryModel.created_at,
            )
        )
        return [_delivery(m) for m in (await self._session.execute(stmt)).scalars()]

    async def order_summaries(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, OrderSummary]:
        """Assemble each order's driver-facing projection with a fixed set of grouped
        queries (orders, lines, payments) — never one query per delivery."""
        if not order_ids:
            return {}

        # Orders + their customer's person (name/phone). Left joins keep walk-in orders.
        order_rows = (
            await self._session.execute(
                select(
                    OrderModel.id,
                    OrderModel.total,
                    PersonModel.first_name,
                    PersonModel.last_name,
                    PersonModel.phone,
                )
                .select_from(OrderModel)
                .outerjoin(CustomerModel, CustomerModel.id == OrderModel.customer_id)
                .outerjoin(PersonModel, PersonModel.id == CustomerModel.person_id)
                .where(
                    OrderModel.tenant_id == tenant_id,
                    OrderModel.id.in_(order_ids),
                )
            )
        ).all()

        # Item lines: product name (+ variant name when set), summed by variant per order.
        line_rows = (
            await self._session.execute(
                select(
                    OrderItemModel.order_id,
                    ProductModel.name,
                    ProductVariantModel.name,
                    OrderItemModel.quantity,
                    OrderItemModel.created_at,
                )
                .select_from(OrderItemModel)
                .join(
                    ProductVariantModel,
                    ProductVariantModel.id == OrderItemModel.product_variant_id,
                )
                .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
                .where(
                    OrderItemModel.tenant_id == tenant_id,
                    OrderItemModel.order_id.in_(order_ids),
                    OrderItemModel.status != _CANCELLED,
                )
                .order_by(OrderItemModel.created_at)
            )
        ).all()

        # Payments: one row per payment; sum settles paid/unpaid, last method is shown.
        payment_rows = (
            await self._session.execute(
                select(
                    OrderPaymentModel.order_id,
                    OrderPaymentModel.method,
                    OrderPaymentModel.amount,
                    OrderPaymentModel.created_at,
                )
                .where(
                    OrderPaymentModel.tenant_id == tenant_id,
                    OrderPaymentModel.order_id.in_(order_ids),
                )
                .order_by(OrderPaymentModel.created_at)
            )
        ).all()

        lines: dict[uuid.UUID, list[OrderLine]] = {}
        for order_id, product_name, variant_name, quantity, _created in line_rows:
            name = f"{product_name} · {variant_name}" if variant_name else product_name
            lines.setdefault(order_id, []).append(OrderLine(name=name, quantity=quantity))

        paid_total: dict[uuid.UUID, Decimal] = {}
        method: dict[uuid.UUID, str] = {}
        for order_id, pay_method, amount, _created in payment_rows:
            paid_total[order_id] = paid_total.get(order_id, Decimal(0)) + amount
            method[order_id] = pay_method  # rows are oldest-first, so last wins

        summaries: dict[uuid.UUID, OrderSummary] = {}
        for order_id, total, first_name, last_name, phone in order_rows:
            name = f"{first_name} {last_name}".strip() if first_name is not None else None
            settled = paid_total.get(order_id, Decimal(0))
            summaries[order_id] = OrderSummary(
                order_id=order_id,
                code=_order_code(order_id),
                total=total,
                paid=total > 0 and settled >= total,
                items=lines.get(order_id, []),
                customer_name=name,
                customer_phone=phone,
                payment_method=method.get(order_id),
            )
        return summaries

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

    async def apply_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        model = await self._get_delivery_model(tenant_id, delivery_id)
        if model is None:
            return None
        order = await self._get_order_model(tenant_id, model.order_id)
        if order is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        fee = fields.get("quoted_fee") or Decimal("0")
        order.delivery_fee = fee
        order.total = order.subtotal - order.discount + fee
        await self._session.commit()
        await self._session.refresh(model)
        return _delivery(model)

    async def list_pending_geocode(self, limit: int) -> list[OrderDelivery]:
        """Every tenant's pin-less deliveries, oldest first. See the port for why cross-tenant.

        `btrim(...) <> ''` and not `is not None`: an address of spaces is not an address, and
        would otherwise sit in the set being retried forever.
        """
        stmt = (
            select(OrderDeliveryModel)
            .where(
                OrderDeliveryModel.latitude.is_(None),
                func.btrim(OrderDeliveryModel.address_text) != "",
            )
            .order_by(OrderDeliveryModel.created_at)
            .limit(limit)
        )
        return [_delivery(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_pending_quotes(self, limit: int) -> list[OrderDelivery]:
        """Pinned deliveries that still want a price.

        `unquotable` is in the set, and that is the whole point of it being a SET and not a
        queue. A delivery is unquotable because of something about the BRANCH — no tariff
        bands, no pin on the map — and the operator fixes those in a screen that knows nothing
        about this row. Leaving it out would strand every order taken before someone configured
        the branch: permanently priceless, invisible to the sweep, waiting for a job that will
        never be enqueued.

        Retrying it costs a Haversine and rewrites the same reason until the branch is fixed.
        """
        stmt = (
            select(OrderDeliveryModel)
            .where(
                OrderDeliveryModel.quote_status.in_(("pending_quote", "unquotable")),
                OrderDeliveryModel.latitude.is_not(None),
                OrderDeliveryModel.longitude.is_not(None),
            )
            .order_by(OrderDeliveryModel.created_at)
            .limit(limit)
        )
        return [_delivery(m) for m in (await self._session.execute(stmt)).scalars()]

    # --- Runs --------------------------------------------------------------
    async def create_run(self, run: DeliveryRun) -> DeliveryRun:
        model = DeliveryRunModel(
            tenant_id=run.tenant_id,
            branch_id=run.branch_id,
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

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> DeliveryRun | None:
        model = await self._get_run_model(tenant_id, run_id)
        return _run(model) if model else None

    async def active_run_for_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DeliveryRun | None:
        stmt = (
            select(DeliveryRunModel)
            .where(
                DeliveryRunModel.tenant_id == tenant_id,
                DeliveryRunModel.employee_id == employee_id,
                DeliveryRunModel.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .order_by(DeliveryRunModel.created_at.desc())
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return _run(model) if model else None

    async def list_runs(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, *, status: str | None = None
    ) -> list[DeliveryRun]:
        stmt = select(DeliveryRunModel).where(
            DeliveryRunModel.tenant_id == tenant_id,
            DeliveryRunModel.branch_id == branch_id,
        )
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

    async def mark_run_deliveries_in_transit(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
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

    # --- Run positions (live driver trail) ---------------------------------
    async def append_position(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        branch_id: uuid.UUID,
        latitude: Decimal,
        longitude: Decimal,
    ) -> RunPosition:
        model = DeliveryRunPositionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            delivery_run_id=run_id,
            latitude=latitude,
            longitude=longitude,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _position(model)

    async def run_trail(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> list[RunPosition]:
        stmt = (
            select(DeliveryRunPositionModel)
            .where(
                DeliveryRunPositionModel.tenant_id == tenant_id,
                DeliveryRunPositionModel.delivery_run_id == run_id,
            )
            .order_by(DeliveryRunPositionModel.recorded_at)
        )
        return [_position(m) for m in (await self._session.execute(stmt)).scalars()]

    async def active_runs_positions(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[ActiveRunTrail]:
        # Inner join to runs, so a run only appears once it has at least one fix, and only
        # while it is active — a finished run's points never reach the dispatcher read.
        stmt = (
            select(DeliveryRunPositionModel, DeliveryRunModel.employee_id)
            .join(
                DeliveryRunModel,
                DeliveryRunModel.id == DeliveryRunPositionModel.delivery_run_id,
            )
            .where(
                DeliveryRunPositionModel.tenant_id == tenant_id,
                DeliveryRunPositionModel.branch_id == branch_id,
                DeliveryRunModel.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .order_by(
                DeliveryRunPositionModel.delivery_run_id,
                DeliveryRunPositionModel.recorded_at,
            )
        )
        trails: dict[uuid.UUID, ActiveRunTrail] = {}
        for model, employee_id in (await self._session.execute(stmt)).all():
            trail = trails.get(model.delivery_run_id)
            if trail is None:
                trail = ActiveRunTrail(
                    run_id=model.delivery_run_id, employee_id=employee_id, trail=[]
                )
                trails[model.delivery_run_id] = trail
            trail.trail.append(_position(model))
        return list(trails.values())

    async def delete_run_positions(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
        await self._session.execute(
            sql_delete(DeliveryRunPositionModel).where(
                DeliveryRunPositionModel.tenant_id == tenant_id,
                DeliveryRunPositionModel.delivery_run_id == run_id,
            )
        )
        await self._session.commit()
