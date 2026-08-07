"""Las reglas de qué puede tocar un cliente en su propio pedido. Funciones puras.

Entran hechos —el estado del pedido, el de sus estaciones, el de su entrega, lo pagado— y sale
un veredicto. Sin base de datos, porque son exactamente las cuatro decisiones que hay que poder
leer y probar de un vistazo, y porque son las que un día alguien va a querer cambiar.

Las cuatro, y por qué cada una:

1. **El total nunca baja.** Sustituye a una lista de verbos permitidos. Una lista envejece mal:
   la primera combinación que nadie previó se cuela. Una invariante sobre el RESULTADO atrapa
   lo que la lista no vio — y hace caer sola la regla que el dueño describió (una gaseosa por
   otra del mismo precio sí, por agua no) sin escribirla en ninguna parte.

2. **Por ítem: sólo si su cocina no empezó.** La granularidad correcta es (ítem × estación), no
   el pedido: la limonada ya lista no puede impedir corregir la hamburguesa que aún no entró a
   la plancha.

3. **Por pedido: hasta que la comida deja de estar al alcance.** Y eso no es "la cocina
   terminó", es un hecho físico que depende de cómo sale el pedido — con entrega, hasta que la
   moto arranca; sin ella, hasta que queda listo en el mostrador. Entre `ready` y `in_transit`
   la bolsa sigue en el pase y un cocinero todavía puede hacer una cosa más.

4. **Con pago, las líneas existentes sólo crecen.** No por el dinero —un cambio a algo más caro
   también sube el total— sino por el registro: si mañana alguien dice "yo pagué por una
   gaseosa negra", tiene que poder contestarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# --- Vocabulario prestado de los módulos observados ---------------------------------------
# Se repiten como texto a propósito: estas reglas no deben importar cocina ni domicilios para
# poder decidir. Son cuatro cadenas, y el precio de repetirlas es mucho menor que el de atar
# este dominio a otros dos.
STATION_PENDING = "pending"
ORDER_OPEN = "open"
KITCHEN_READY = "ready"
DELIVERY_GONE = ("in_transit", "delivered", "not_delivered")


@dataclass(frozen=True)
class OrderFacts:
    """Lo que hay que saber del pedido para decidir si se puede tocar."""

    status: str
    kitchen_state: str
    #: Estado de su entrega, o `None` si este pedido no se reparte (mostrador, mesa).
    delivery_status: str | None
    total: Decimal
    paid: Decimal

    @property
    def is_paid(self) -> bool:
        """Pagado = lo recibido cubre el total. Pagar NO cierra la comanda."""
        return self.paid >= self.total and self.total > 0


class EditRefusal(str):
    """El motivo, en un código que el front traduce a una frase."""


REFUSAL_ORDER_CLOSED = EditRefusal("order_closed")
REFUSAL_OUT_OF_REACH = EditRefusal("out_of_reach")
REFUSAL_ITEM_STARTED = EditRefusal("item_started")
REFUSAL_TOTAL_WOULD_DROP = EditRefusal("total_would_drop")
REFUSAL_PAID_LINE = EditRefusal("paid_line")


def order_window(order: OrderFacts) -> EditRefusal | None:
    """`None` si el pedido admite cambios; si no, el motivo por el que ya no.

    El orden de las comprobaciones es el orden en que se le explican a una persona: primero
    "ese pedido ya se cerró", después "ya salió".
    """
    if order.status != ORDER_OPEN:
        return REFUSAL_ORDER_CLOSED

    if order.delivery_status is not None:
        # Se reparte: la comida está al alcance hasta que la moto arranca.
        if order.delivery_status in DELIVERY_GONE:
            return REFUSAL_OUT_OF_REACH
        return None

    # Sin entrega no hay "salir": la comida espera en el mostrador desde que está lista, y
    # desde ese momento el cliente puede aparecer a recogerla en cualquier segundo.
    if order.kitchen_state == KITCHEN_READY:
        return REFUSAL_OUT_OF_REACH
    return None


def item_window(station_statuses: list[str]) -> EditRefusal | None:
    """`None` si ese ítem todavía no lo empezó nadie.

    Un ítem sin estaciones (aún no enviado a cocina) es editable: no hay nada empezado.
    """
    if any(status != STATION_PENDING for status in station_statuses):
        return REFUSAL_ITEM_STARTED
    return None


def total_invariant(before: Decimal, after: Decimal) -> EditRefusal | None:
    """`None` si el total no bajó.

    Se compara el pedido RESULTANTE contra el anterior, nunca operación por operación: un
    cambio de producto es "quitar y poner", y validado por pasos el intermedio siempre bajaría
    y ningún cambio sería posible jamás.
    """
    if after < before:
        return REFUSAL_TOTAL_WOULD_DROP
    return None


def paid_line_change(order: OrderFacts, changes_line_identity: bool) -> EditRefusal | None:
    """`None` salvo que se intente cambiar de producto una línea ya pagada.

    Crecer sí —adiciones, cantidad—: eso deja lo pagado donde estaba y añade encima. Cambiar
    de producto reescribe algo que ya se cobró, y entonces "¿por qué me cobraron esto?" deja de
    tener respuesta.
    """
    if order.is_paid and changes_line_identity:
        return REFUSAL_PAID_LINE
    return None
