"""Payment use case for the Orders module — the orders ↔ cash integration.

Charging an order registers an `order_payments` row tied to the branch's open
cash session and, atomically, a `cash_movements` row (type `in`, concept `sale`)
so the arqueo reflects the sale. Payments do not change the order status.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from restaurante.modules.orders.domain.entities import (
    CLAIM_ACCEPTED,
    CLAIM_REJECTED,
    Order,
    OrderPayment,
    OrderPaymentClaim,
    OrderRefund,
)
from restaurante.modules.orders.domain.ports import (
    DeliveryQuoteGate,
    KitchenRouting,
    OrdersRepository,
    PaymentClaimNotifier,
)
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

ORDER_OPEN = "open"
#: Tope de declaraciones esperando a una persona por pedido. No es por el disco: es para que la
#: comanda siga siendo una decisión de un vistazo y no una lista de intentos.
MAX_PENDING_CLAIMS = 3
# El efectivo se cobra en la puerta; todo lo demás llega pagado y hay que verificarlo antes
# de cocinar.
METHOD_CASH = "cash"


class PaymentService:
    def __init__(
        self,
        repo: OrdersRepository,
        kitchen_routing: KitchenRouting | None = None,
        customer_notifier: PaymentClaimNotifier | None = None,
        quote_gate: DeliveryQuoteGate | None = None,
    ) -> None:
        self._repo = repo
        # Puerto opcional: con él cableado, verificar un pago prepagado también enruta a cocina.
        self._kitchen_routing = kitchen_routing
        # Otro opcional: sin él, resolver un comprobante no avisa a nadie y todo lo demás
        # funciona igual — que es como se comportaba antes de que existieran.
        self._customer_notifier = customer_notifier
        # Y otro: sin él la puerta del domicilio está abierta y verificar se comporta como
        # siempre. Con él, un domicilio sin cotizar no se cobra ni llega a cocina.
        self._quote_gate = quote_gate

    async def _require_open_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        if order.status != ORDER_OPEN:
            raise ConflictError(
                f"La orden no está abierta (estado: {order.status})."
            )
        return order

    async def register_payment(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
        method: str,
        employee_id: uuid.UUID,
        diner_reference: str | None = None,
    ) -> OrderPayment:
        order = await self._require_open_order(tenant_id, order_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        if amount <= 0:
            raise ValidationError("El monto del pago debe ser positivo.")
        session = await self._repo.get_open_cash_session(tenant_id, order.branch_id)
        if session is None:
            raise ConflictError(
                "No hay sesión de caja abierta en la sucursal para registrar el pago."
            )
        assert session.id is not None
        return await self._repo.register_payment(
            OrderPayment(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                cash_session_id=session.id,
                amount=amount,
                method=method,
                employee_id=employee_id,
                diner_reference=diner_reference,
            )
        )

    async def verify_payment(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Order:
        """Dar por bueno el pago de un pedido prepagado y mandarlo a cocina, en un gesto.

        Quien atiende mira el comprobante de la transferencia o el Nequi y confirma. Ese "ok"
        es el que registra el cobro y dispara la cocina: son el mismo momento mental, y
        separarlos crearía el estado "verificado pero sin cocinar" que nadie mira.

        Se cobra primero y se enruta después, a propósito. Si el cobro falla no pasa nada más
        —el pedido queda sin pagar y sin cocinar, que es lo correcto—. Si falla el enrutado
        después de cobrar, basta con volver a verificar: es idempotente y no cobra dos veces.
        """
        order = await self._require_open_order(tenant_id, order_id)
        if (order.payment_method or METHOD_CASH) == METHOD_CASH:
            raise ValidationError(
                "Un pedido en efectivo no se verifica: se cobra al entregarlo."
            )
        # Antes de tocar dinero: un domicilio sin cotizar tiene un total que aún no incluye el
        # domicilio. Cobrarlo aquí cobra de menos Y abre la cocina, y para cuando alguien lo
        # note el pedido va de camino.
        await self._require_quotable(tenant_id, order_id)

        paid = await self._repo.payments_total(tenant_id, order_id)
        remainder = order.total - paid
        if remainder > 0:
            await self.register_payment(
                tenant_id,
                order_id,
                remainder,
                order.payment_method or METHOD_CASH,
                employee_id,
            )
        if self._kitchen_routing is not None:
            await self._kitchen_routing.route_order(tenant_id, order_id)
        # Lo que el cliente mandó queda dado por bueno por quien acaba de mirarlo.
        await self._accept_pending_claims(tenant_id, order_id, employee_id)
        refreshed = await self._repo.get_order(tenant_id, order_id)
        return refreshed or order

    async def _require_quotable(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Levanta si el domicilio del pedido aún no puede cobrarse.

        Sin puerta enchufada no bloquea nada: un despliegue sin domicilios se comporta
        exactamente como antes.
        """
        if self._quote_gate is None:
            return
        blocker = await self._quote_gate.quote_blocker(tenant_id, order_id)
        if blocker is not None:
            raise ConflictError(blocker)

    async def is_payment_verified(
        self, tenant_id: uuid.UUID, order: Order
    ) -> bool:
        """True cuando el pedido puede pasar a cocina por su lado del dinero.

        El efectivo siempre puede: su plata llega en la puerta. El prepago necesita que los
        pagos registrados cubran el total.
        """
        if (order.payment_method or METHOD_CASH) == METHOD_CASH:
            return True
        if order.id is None:
            return False
        paid = await self._repo.payments_total(tenant_id, order.id)
        return paid >= order.total

    # --- Declaraciones de pago del cliente -----------------------------------
    # Lo que el cliente DICE que pagó. Nada de esto registra dinero: no suma a `payments_total`,
    # no abre la cocina y no cambia el estado del pedido. Sólo `verify_payment` cobra.
    async def declare_payment(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
        method: str,
        proof_url: str | None = None,
    ) -> OrderPaymentClaim:
        order = await self._require_open_order(tenant_id, order_id)
        if amount <= 0:
            raise ValidationError("El monto declarado debe ser positivo.")
        pending = await self._repo.count_pending_payment_claims(tenant_id, order_id)
        if pending >= MAX_PENDING_CLAIMS:
            raise ConflictError(
                "Ya hay comprobantes esperando confirmación para este pedido."
            )
        return await self._repo.create_payment_claim(
            OrderPaymentClaim(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                amount=amount,
                method=method,
                proof_url=proof_url,
            )
        )

    async def list_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPaymentClaim]:
        return await self._repo.list_payment_claims(tenant_id, order_id)

    async def has_pending_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool:
        return await self._repo.count_pending_payment_claims(tenant_id, order_id) > 0

    async def reject_payment_claim(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        claim_id: uuid.UUID,
        reason: str,
        employee_id: uuid.UUID,
    ) -> OrderPaymentClaim:
        """Rechazar no cobra nada y deja al cliente poder mandar otro comprobante.

        El motivo es obligatorio porque es lo único que el cliente va a leer: "no nos sirve"
        no le dice si mandar otra foto, corregir la cifra o llamar.
        """
        if not reason.strip():
            raise ValidationError("Un rechazo necesita un motivo.")
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        resolved = await self._repo.resolve_payment_claims(
            tenant_id,
            order_id,
            status=CLAIM_REJECTED,
            employee_id=employee_id,
            reason=reason.strip(),
            claim_id=claim_id,
        )
        if not resolved:
            raise NotFoundError("Ese comprobante no está pendiente.")
        claim = resolved[0]
        await self._notify_claim(tenant_id, order_id, claim)
        return claim

    async def _accept_pending_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        """Da por buenas las declaraciones pendientes tras verificar el pago.

        Se llama DESPUÉS de cobrar y enrutar, y su fallo no puede deshacer aquello: el dinero
        ya está registrado, y dejar una declaración en `pending` es un desajuste visible que
        alguien resuelve, no una venta perdida.

        Se aceptan TODAS las pendientes y se avisa UNA vez. Para el cliente, que le confirmen el
        pago es un solo hecho: cuántas veces lo declaró es contabilidad nuestra. Avisar por
        declaración le mandaba el mismo mensaje dos veces, y eso pasa de forma natural —dice "ya
        pagué" desde el enlace de pago (sin soporte) y después manda la foto por WhatsApp, que
        alguien reclama desde el chat: dos declaraciones para un solo pago.
        """
        accepted = await self._repo.resolve_payment_claims(
            tenant_id, order_id, status=CLAIM_ACCEPTED, employee_id=employee_id
        )
        if accepted:
            await self._notify_claim(tenant_id, order_id, accepted[0])

    async def _notify_claim(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, claim: OrderPaymentClaim
    ) -> None:
        """Le dice al cliente en qué quedó su comprobante. Sin canal, no pasa nada.

        Avisar no puede tumbar el cobro: el dinero ya se registró, y un WhatsApp que no sale
        no puede convertirse en una venta que no ocurrió.
        """
        if self._customer_notifier is None:
            return
        try:
            await self._customer_notifier.notify_payment_claim(
                tenant_id, order_id, claim.status, claim.rejection_reason
            )
        except Exception:  # noqa: BLE001 - avisar nunca puede costar el cobro
            logger.warning(
                "No se pudo avisar del comprobante del pedido %s", order_id, exc_info=True
            )

    # --- Devoluciones --------------------------------------------------------
    async def open_refund_if_prepaid(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderRefund | None:
        """Abre la deuda de devolución de un pedido no entregado que ya estaba pagado.

        El efectivo nunca la genera: se cobra en la puerta, así que un pedido no entregado en
        efectivo nunca se pagó y no hay nada que devolver. Sólo lo prepagado se devuelve — y lo
        prepagado nunca tocó el cajón, que es lo que hace que el arqueo no se mueva.
        """
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            return None
        paid = await self._repo.payments_total(tenant_id, order_id)
        if paid <= 0:
            return None
        if await self._repo.refund_for_order(tenant_id, order_id) is not None:
            return None  # Marcar dos veces no entregada no duplica la deuda.
        payments = await self._repo.list_payments(tenant_id, order_id)
        method = payments[-1].method if payments else (order.payment_method or "transfer")
        return await self._repo.create_refund(
            OrderRefund(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                amount=paid,
                method=method,
            )
        )

    async def list_refunds(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = "pending",
    ) -> list[OrderRefund]:
        return await self._repo.list_refunds(tenant_id, branch_id, status=status)

    async def confirm_refund(
        self, tenant_id: uuid.UUID, refund_id: uuid.UUID, employee_id: uuid.UUID
    ) -> OrderRefund:
        """La plata salió de verdad: se registra el movimiento con el método original."""
        refund = await self._require_pending_refund(tenant_id, refund_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        # El movimiento primero: si la caja no lo admite, la devolución sigue pendiente y
        # alguien puede reintentarla. Marcarla hecha sin movimiento la perdería de vista.
        await self._repo.register_refund_movement(refund)
        resolved = await self._repo.resolve_refund(
            tenant_id, refund_id, status="done", employee_id=employee_id, reason=None
        )
        if resolved is None:
            raise ConflictError("La devolución ya fue resuelta.")
        return resolved

    async def cancel_refund(
        self,
        tenant_id: uuid.UUID,
        refund_id: uuid.UUID,
        employee_id: uuid.UUID,
        reason: str,
    ) -> OrderRefund:
        """No se devuelve: se arregló de otra forma. Exige motivo, y no mueve un peso."""
        if not reason or not reason.strip():
            raise ValidationError("Cancelar una devolución exige un motivo.")
        await self._require_pending_refund(tenant_id, refund_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        resolved = await self._repo.resolve_refund(
            tenant_id,
            refund_id,
            status="cancelled",
            employee_id=employee_id,
            reason=reason.strip(),
        )
        if resolved is None:
            raise ConflictError("La devolución ya fue resuelta.")
        return resolved

    async def _require_pending_refund(
        self, tenant_id: uuid.UUID, refund_id: uuid.UUID
    ) -> OrderRefund:
        refund = await self._repo.get_refund(tenant_id, refund_id)
        if refund is None:
            raise NotFoundError(f"Devolución no encontrada: {refund_id}")
        if refund.status != "pending":
            raise ConflictError(
                f"La devolución ya fue resuelta (estado: {refund.status})."
            )
        return refund

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPayment]:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        return await self._repo.list_payments(tenant_id, order_id)
