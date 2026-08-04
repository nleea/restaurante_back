"""Cancelar una comanda suelta su entrega, igual que suelta su mesa.

La asimetría era el bug: `cancel_order` liberaba la mesa y abandonaba la entrega. La fila se
quedaba `pending` con su comanda muerta detrás, sin poder llegar nunca a cocina, y bloqueando el
cierre de caja del turno sin más salida que mentir ("no entregada").
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    D_ASSIGNED,
    D_CANCELLED,
    D_IN_TRANSIT,
    D_PENDING,
    DeliveryService,
)
from restaurante.modules.delivery.domain.entities import OrderDelivery
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.domain.entities import Order

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()
ORDER = uuid.uuid4()
DELIVERY = uuid.uuid4()
EMPLOYEE = uuid.uuid4()


class FakeDeliveryRepo:
    """El repositorio de delivery, con una entrega en el estado que se quiera."""

    def __init__(self, delivery: OrderDelivery | None) -> None:
        self._delivery = delivery
        self.updates: list[dict[str, object]] = []

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery | None:
        return self._delivery

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, object]
    ) -> None:
        self.updates.append(fields)


def _delivery(status: str) -> OrderDelivery:
    return OrderDelivery(
        id=DELIVERY,
        tenant_id=TENANT,
        branch_id=BRANCH,
        order_id=ORDER,
        address_text="Calle 1 #2-3",
        delivery_status=status,
    )


def _service(delivery: OrderDelivery | None) -> tuple[DeliveryService, FakeDeliveryRepo]:
    repo = FakeDeliveryRepo(delivery)
    return DeliveryService(repo), repo  # type: ignore[arg-type]


class TestReleasingTheDelivery:
    @pytest.mark.asyncio
    async def test_a_delivery_that_never_left_is_cancelled(self) -> None:
        service, repo = _service(_delivery(D_PENDING))

        released = await service.release_delivery_for_order(TENANT, ORDER)

        assert released is True
        assert repo.updates[0]["delivery_status"] == D_CANCELLED
        # Con su sello de cierre: es un desenlace, no un limbo nuevo.
        assert repo.updates[0]["delivered_at"] is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [D_ASSIGNED, D_IN_TRANSIT])
    async def test_a_delivery_already_out_is_left_alone(self, status: str) -> None:
        """Alguien salió con esa comida. Cancelarla en silencio le borraría la parada del móvil."""
        service, repo = _service(_delivery(status))

        released = await service.release_delivery_for_order(TENANT, ORDER)

        assert released is False
        assert repo.updates == []

    @pytest.mark.asyncio
    async def test_an_already_resolved_delivery_is_left_alone(self) -> None:
        service, repo = _service(_delivery(D_CANCELLED))

        assert await service.release_delivery_for_order(TENANT, ORDER) is False
        assert repo.updates == []

    @pytest.mark.asyncio
    async def test_an_order_with_no_delivery_is_not_an_error(self) -> None:
        """La mayoría de las comandas no son domicilios."""
        service, repo = _service(None)

        assert await service.release_delivery_for_order(TENANT, ORDER) is False
        assert repo.updates == []


class ExplodingDispatch:
    async def ensure_delivery_for_order(self, *a: object, **k: object) -> None: ...

    async def release_delivery_for_order(self, *a: object, **k: object) -> None:
        raise RuntimeError("delivery está caído")


class RecordingDispatch:
    def __init__(self) -> None:
        self.released: list[uuid.UUID] = []

    async def ensure_delivery_for_order(self, *a: object, **k: object) -> None: ...

    async def release_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        self.released.append(order_id)


class FakeOrdersRepo:
    """Lo mínimo que `cancel_order` toca."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.cancellations = 0

    async def get_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order:
        return Order(
            id=ORDER,
            tenant_id=TENANT,
            branch_id=BRANCH,
            channel=self.channel,
            employee_id=EMPLOYEE,
            status="open",
            subtotal=Decimal("10000"),
            total=Decimal("10000"),
        )

    async def employee_exists(self, tenant_id: uuid.UUID, employee_id: uuid.UUID) -> bool:
        return True

    async def create_cancellation(self, cancellation: object) -> None:
        self.cancellations += 1

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, object]
    ) -> Order:
        return await self.get_order(tenant_id, order_id)

    async def update_dining_table(self, *a: object, **k: object) -> None: ...

    # --- lo que además toca `close_order` ---
    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal:
        return Decimal("10000")  # pagada del todo: el cierre procede

    async def consume_inventory_for_order(self, *a: object, **k: object) -> None: ...

    async def close_order(self, *a: object, **k: object) -> Order:
        return await self.get_order(TENANT, ORDER)


class TestCancellingAnOrder:
    @pytest.mark.asyncio
    async def test_a_delivery_order_releases_its_delivery(self) -> None:
        dispatch = RecordingDispatch()
        service = OrderService(FakeOrdersRepo("delivery"), delivery_dispatch=dispatch)  # type: ignore[arg-type]

        await service.cancel_order(TENANT, ORDER, "cliente se arrepintió", EMPLOYEE)

        assert dispatch.released == [ORDER]

    @pytest.mark.asyncio
    async def test_a_dine_in_order_looks_for_no_delivery(self) -> None:
        dispatch = RecordingDispatch()
        service = OrderService(FakeOrdersRepo("dine_in"), delivery_dispatch=dispatch)  # type: ignore[arg-type]

        await service.cancel_order(TENANT, ORDER, "mesa equivocada", EMPLOYEE)

        assert dispatch.released == []

    @pytest.mark.asyncio
    async def test_a_failure_releasing_never_costs_the_cancellation(self) -> None:
        """No poder soltar la entrega no puede dejar viva una comanda que alguien canceló."""
        repo = FakeOrdersRepo("delivery")
        service = OrderService(repo, delivery_dispatch=ExplodingDispatch())  # type: ignore[arg-type]

        result = await service.cancel_order(TENANT, ORDER, "se cayó delivery", EMPLOYEE)

        assert result is not None
        assert repo.cancellations == 1

    @pytest.mark.asyncio
    async def test_without_the_port_cancelling_behaves_as_before(self) -> None:
        """Un despliegue sin domicilios cancela igual que siempre."""
        repo = FakeOrdersRepo("delivery")
        service = OrderService(repo)  # type: ignore[arg-type]

        result = await service.cancel_order(TENANT, ORDER, "sin módulo", EMPLOYEE)

        assert result is not None
        assert repo.cancellations == 1


class TestClosingIsNotCancelling:
    """Cerrar y cancelar NO son lo mismo, y confundirlos borra domicilios pagados.

    Cerrar significa que la comanda está pagada y SIGUE su camino: cocina y luego despacho. Su
    entrega está en `pending` esperando que la asignen a un domiciliario — exactamente el estado
    que la liberación toca. Soltarla al cerrar la sacaría del tablero y el pedido, ya cobrado, no
    lo llevaría nadie.

    Cancelar es lo contrario: la comanda deja de existir, así que su entrega también.
    """

    @pytest.mark.asyncio
    async def test_closing_a_delivery_order_leaves_its_delivery_alone(self) -> None:
        dispatch = RecordingDispatch()
        service = OrderService(FakeOrdersRepo("delivery"), delivery_dispatch=dispatch)  # type: ignore[arg-type]

        await service.close_order(TENANT, ORDER)

        assert dispatch.released == [], (
            "cerrar soltó la entrega: el domicilio pagado desaparecería del despacho"
        )

    @pytest.mark.asyncio
    async def test_cancelling_still_releases_it(self) -> None:
        """El control: la liberación sigue viva donde SÍ corresponde."""
        dispatch = RecordingDispatch()
        service = OrderService(FakeOrdersRepo("delivery"), delivery_dispatch=dispatch)  # type: ignore[arg-type]

        await service.cancel_order(TENANT, ORDER, "cliente se arrepintió", EMPLOYEE)

        assert dispatch.released == [ORDER]


class TestTheWiring:
    """El servicio hacía lo correcto y en producción no pasaba nada.

    Todas las pruebas de arriba construyen el `OrderService` a mano con el puerto puesto. El
    endpoint de cancelar usaba uno construido en `deps.py` SIN el puerto, así que
    `_release_delivery` salía por la primera línea y la entrega seguía bloqueando la caja.

    Un doble bien montado no prueba que el composition root lo monte igual.
    """

    async def test_the_cancel_endpoint_service_can_release_deliveries(self) -> None:
        from restaurante.modules.orders.infrastructure.api.deps import get_order_service
        from restaurante.shared.database import SessionFactory

        async with SessionFactory() as session:
            service = get_order_service(session)

        assert service._delivery_dispatch is not None, (
            "el servicio que atiende cancelar/cerrar no puede soltar la entrega: "
            "sin el puerto, una comanda cancelada deja su domicilio bloqueando la caja"
        )

    async def test_it_really_reaches_the_delivery_module(self) -> None:
        """No basta con que no sea None: tiene que saber soltar, no sólo crear."""
        from restaurante.modules.orders.infrastructure.api.deps import get_order_service
        from restaurante.shared.database import SessionFactory

        async with SessionFactory() as session:
            dispatch = get_order_service(session)._delivery_dispatch

        assert hasattr(dispatch, "release_delivery_for_order")
