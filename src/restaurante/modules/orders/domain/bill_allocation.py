"""Repartir lo que se cobra en una mesa entre las comandas que la componen.

Función pura: entran los miembros y los pagos, salen las asignaciones. Sin base de datos y sin
efectos, porque esto toca dinero y la aritmética tiene que poder probarse a mano.

**En cascada, no a prorrata.** Cada pago llena la primera comanda hasta su total antes de pasar a
la siguiente:

    Ana $32.000   Luis $54.000   Sofía $34.000        cobro: $120.000 en efectivo
      → Ana  32.000 · Luis 54.000 · Sofía 34.000

    tarjeta $80.000  +  efectivo $40.000
      → Ana  32.000 tarjeta
      → Luis 48.000 tarjeta + 6.000 efectivo    ← una comanda con dos métodos: ya se sabe hacer
      → Sofía 34.000 efectivo

La prorrata partiría cada pago en pedazos que nadie pidió, produciría centavos que hay que
redondear y dejaría devoluciones ilegibles ("devolver $17.333 del pago de tarjeta"). La cascada
produce importes que un humano reconoce.

**El orden es parte del contrato**, no un detalle: dos cobros idénticos tienen que repartir
igual. Lo fija quien llama, ordenando por `created_at` y desempatando por `id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BillMember:
    """Una comanda de la cuenta y lo que le falta por cubrir."""

    order_id: object
    outstanding: Decimal


@dataclass(frozen=True)
class BillPayment:
    """Un cobro del gesto del cajero: un importe y con qué se pagó."""

    amount: Decimal
    method: str


@dataclass(frozen=True)
class Allocation:
    """Lo que hay que registrar sobre UNA comanda: un pago real, con su método."""

    order_id: object
    amount: Decimal
    method: str


@dataclass(frozen=True)
class AllocationResult:
    allocations: list[Allocation]
    #: Lo que sigue sin cubrirse. Cero = la cuenta se puede liquidar.
    uncovered: Decimal
    #: Lo que sobró del último pago. Es vuelto, y la regla de sobrepago ya lo trata así.
    change: Decimal


def allocate(
    members: list[BillMember], payments: list[BillPayment]
) -> AllocationResult:
    """Reparte `payments` sobre `members` en cascada, respetando el orden recibido.

    No decide nada sobre el mundo: no valida sesiones de caja, no cierra comandas y no sabe si
    la cuenta se puede liquidar. Devuelve qué habría que escribir y cuánto falta; quien llama
    decide qué hacer con eso.
    """
    allocations: list[Allocation] = []
    remaining_by_member = [(m.order_id, m.outstanding) for m in members]
    index = 0
    change = Decimal("0")

    for payment in payments:
        left = payment.amount
        while left > 0 and index < len(remaining_by_member):
            order_id, owed = remaining_by_member[index]
            if owed <= 0:
                index += 1
                continue
            take = min(left, owed)
            allocations.append(
                Allocation(order_id=order_id, amount=take, method=payment.method)
            )
            remaining_by_member[index] = (order_id, owed - take)
            left -= take
            if remaining_by_member[index][1] == 0:
                index += 1
        # Lo que queda cuando ya no hay comanda que cubrir es vuelto. Se acumula en vez de
        # asignarse a nadie: no es de ninguna comanda, es dinero que vuelve al cliente.
        if left > 0:
            change += left

    uncovered = sum((owed for _, owed in remaining_by_member), Decimal("0"))
    return AllocationResult(
        allocations=allocations, uncovered=uncovered, change=change
    )
