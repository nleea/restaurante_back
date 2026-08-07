"""La puerta que impide cobrar un domicilio antes de que tenga precio.

El agujero que cierra es de orden, no de permisos: un domicilio se crea ANTES de que exista su
tarifa —eso es todo el diseño de la cotización diferida— así que entre la toma y la cotización
hay una ventana en la que `orders.total` es sólo la comida. Verificar el pago ahí cobra de menos
Y abre la cocina, y para cuando alguien lo nota el pedido va de camino.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from restaurante.modules.orders.application.use_cases.manage_payments import (
    PaymentService,
)
from restaurante.shared.domain.errors import ConflictError

TENANT = uuid.uuid4()
ORDER = uuid.uuid4()


class FakeGate:
    """La puerta, con la respuesta ya decidida. Aquí se prueba QUÉ HACE quien la consulta."""

    def __init__(self, blocker: str | None) -> None:
        self._blocker = blocker
        self.asked = 0

    async def quote_blocker(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> str | None:
        self.asked += 1
        return self._blocker


class FakeOrder:
    id = ORDER
    branch_id = uuid.uuid4()
    status = "open"
    payment_method = "transfer"
    total = Decimal("38000")


class FakeRepo:
    """Lo mínimo que `verify_payment` toca antes de llegar al dinero."""

    def __init__(self) -> None:
        self.registered: list[Decimal] = []

    async def get_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> FakeOrder:
        return FakeOrder()

    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal:
        return Decimal("0")

    async def employee_exists(self, tenant_id: uuid.UUID, employee_id: uuid.UUID) -> bool:
        return True

    async def get_open_cash_session(self, tenant_id: uuid.UUID, branch_id: uuid.UUID):
        raise AssertionError("no debía llegarse a cobrar")


class ExplodingKitchen:
    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
        raise AssertionError("la cocina no debía recibir nada")


class TestVerifyingIsRefusedBeforeAQuote:
    @pytest.mark.asyncio
    async def test_a_pending_quote_blocks_money_and_kitchen(self) -> None:
        gate = FakeGate("El domicilio de este pedido todavía no tiene valor calculado.")
        service = PaymentService(
            repo=FakeRepo(),  # type: ignore[arg-type]
            kitchen_routing=ExplodingKitchen(),  # type: ignore[arg-type]
            quote_gate=gate,  # type: ignore[arg-type]
        )

        with pytest.raises(ConflictError) as err:
            await service.verify_payment(TENANT, ORDER, uuid.uuid4())

        # El mensaje es para una PERSONA que tiene al cliente delante.
        assert "todavía no tiene valor calculado" in str(err.value)
        assert gate.asked == 1

    @pytest.mark.asyncio
    async def test_the_gate_is_asked_before_anything_is_charged(self) -> None:
        """`FakeRepo.get_open_cash_session` revienta: si se llega a cobrar, el test falla."""
        service = PaymentService(
            repo=FakeRepo(),  # type: ignore[arg-type]
            quote_gate=FakeGate("sin cotizar"),  # type: ignore[arg-type]
        )

        with pytest.raises(ConflictError):
            await service.verify_payment(TENANT, ORDER, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_without_a_gate_nothing_changes(self) -> None:
        """Un despliegue sin domicilios se comporta exactamente como antes."""
        service = PaymentService(repo=FakeRepo())  # type: ignore[arg-type]

        # Llega hasta el cobro — que es donde el fake revienta. Eso prueba que la puerta no
        # bloqueó: sin ella, `verify_payment` sigue su camino de siempre.
        with pytest.raises(AssertionError, match="no debía llegarse a cobrar"):
            await service.verify_payment(TENANT, ORDER, uuid.uuid4())
