"""La frase que contesta "¿cómo va mi pedido?" sin depender de nadie.

Función pura, como `faq.py` y `templates.py`: sin base de datos, sin red, sin reloj. Quien llama
trae el hecho ya leído.

**No deriva el estado de cliente completo.** Esa regla es de `orders` —la transición que dispara
el aviso— y copiarla aquí sería una segunda verdad que se queda vieja el día que cambie. Lo que
hace esto es leer los hechos que sí tenemos (estado, cocina y domicilio) y decir el más avanzado,
que es lo que el cliente espera oír.
"""

from __future__ import annotations

from restaurante.modules.messaging.domain.ports import ContactOrder

# Estados de entrega, tal y como los persiste `delivery` en `order_deliveries.delivery_status`.
_DELIVERY_STATUS_LINES: dict[str, str] = {
    "assigned": "ya tiene domiciliario asignado",
    "in_transit": "va en camino",
    "not_delivered": "no se pudo entregar",
}


def customer_status_line(order: ContactOrder) -> str:
    """El estado del pedido en una frase, del desenlace hacia atrás.

    El orden importa: un pedido cancelado no "va en camino" aunque su entrega tenga un estado
    previo, y uno cerrado ya terminó. Se pregunta primero por lo terminal y después por lo
    operativo, que es el orden en que el cliente lo vive.
    """
    if order.status == "cancelled":
        return "fue cancelado"
    if order.status == "closed":
        return "fue entregado y cerrado"
    if order.delivery_status in _DELIVERY_STATUS_LINES:
        return _DELIVERY_STATUS_LINES[order.delivery_status]
    if order.kitchen_state == "ready":
        return "ya está listo"
    if order.kitchen_state == "in_kitchen":
        return "está en cocina"
    return "lo recibimos y está en proceso"
