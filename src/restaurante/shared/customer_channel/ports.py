"""Puertos del canal con el cliente.

Dos puertos, porque son dos preguntas distintas:

- `CustomerNotifier` — "este pedido pasó a tal estado; avísale al cliente si toca".
  Lo usan `orders` y `delivery`, que no saben ni quieren saber que existe WhatsApp.
- `CustomerChannelDirectory` — "¿de quién es este token del enlace?". Lo usa el
  storefront público para precargar el checkout.

Ambos son **best-effort por contrato**: una transición de pedido no puede fallar
porque el puente de WhatsApp esté caído. El implementador traga y registra.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

# Estados del pedido tal y como los ve el CLIENTE. No son los estados internos: la
# comanda pasa por `pending`/`in_progress`/`preparing` y al cliente no le dice nada de
# eso. Cada uno de estos es un mensaje que puede salir a un teléfono, y por eso la lista
# es corta y cerrada.
CUSTOMER_STATE_ORDER_RECEIVED = "order_received"
# El acuse de un pedido que nace debiendo: sustituye al de arriba, no se suma. Un prepago sin
# verificar no está "en preparación" —la cocina no lo ha visto— y decirle al cliente que sí es la
# fábrica de "¿ya está listo?" y de decepciones en la puerta.
CUSTOMER_STATE_AWAITING_PROOF = "awaiting_proof"
CUSTOMER_STATE_READY = "ready"
CUSTOMER_STATE_ASSIGNED = "assigned"
CUSTOMER_STATE_ON_THE_WAY = "on_the_way"
CUSTOMER_STATE_DELIVERED = "delivered"
CUSTOMER_STATE_CANCELLED = "cancelled"

CUSTOMER_STATES: tuple[str, ...] = (
    CUSTOMER_STATE_ORDER_RECEIVED,
    CUSTOMER_STATE_AWAITING_PROOF,
    CUSTOMER_STATE_READY,
    CUSTOMER_STATE_ASSIGNED,
    CUSTOMER_STATE_ON_THE_WAY,
    CUSTOMER_STATE_DELIVERED,
    CUSTOMER_STATE_CANCELLED,
)


class CustomerNotifier(Protocol):
    """Puerto de salida: contarle al cliente que su pedido cambió de estado.

    `notify_order_state` NUNCA levanta. Quien la llama está en mitad de una transición
    de negocio ya decidida (el domiciliario salió, la comanda se canceló) y un fallo de
    mensajería no puede deshacerla.
    """

    async def notify_order_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None: ...


# ¿Llegó el mensaje al cliente? Vocabulario del canal, no de un módulo: `delivery` lo persiste
# y `messaging` lo produce, y ninguno de los dos debería tener que importar al otro.
#
# Deliberadamente separado del `status` de una solicitud de pago (pendiente/usada/invalidada):
# un enlace puede estar perfectamente vivo y no haberse entregado nunca, y ésa es justo la fila
# que un despachador tiene que perseguir.
EMISSION_PENDING = "pending"
EMISSION_SENT = "sent"
EMISSION_FAILED = "failed"
# No falló nada y no se mandó nada: el pedido no tiene contacto de WhatsApp al que escribirle.
# Un pedido de mostrador es el caso común, así que esto no es un fallo — es un relevo a una
# persona.
EMISSION_NO_CONTACT = "no_contact"


@dataclass(frozen=True)
class EmissionOutcome:
    """Whether a one-shot customer message went out, and why not when it did not.

    `notify_order_state` returns nothing because a lost status ping costs nothing. This one
    reports back, because its caller holds a payment link that only exists in memory: if the
    message did not go out, the link is gone and a human has to be told. Reporting is not
    raising — the contract below still forbids that.
    """

    sent: bool
    # Machine-readable, from `EMISSION_*` in `delivery.domain.entities`, so a caller can store
    # "nobody to write to" differently from "the bridge is down".
    status: str
    reason: str | None = None


class DeliveryPaymentRequestNotifier(Protocol):
    """Puerto de salida: entregarle al cliente el enlace de pago de su domicilio.

    `notify_delivery_payment_request` NUNCA levanta: devuelve `EmissionOutcome`. Quien la llama
    acaba de congelar una cotización y de acuñar un enlace de un solo uso, y un puente caído no
    puede deshacer ninguna de las dos cosas — sólo dejar constancia de que el cliente no recibió
    nada.

    El enlace llega ya construido porque el token en claro sólo existe dentro de la pasada que
    creó la solicitud; este puerto no puede ir a buscarlo a la base.

    `request_id` es la clave de deduplicación, y va aparte de `payment_url` a propósito: la URL
    lleva el token en claro, así que usarla como clave lo escribiría en la tabla de emisiones —
    exactamente la credencial que la solicitud guarda hasheada.
    """

    async def notify_delivery_payment_request(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        request_id: uuid.UUID,
        payment_url: str,
        delivery_fee: Decimal,
    ) -> EmissionOutcome: ...


@dataclass
class ChannelContact:
    """A quién resuelve un token del enlace de la carta.

    Sólo datos de contacto y la sede: el token NO resuelve a un pedido, así que un
    enlace filtrado no puede leer el historial de nadie.
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    contact_id: uuid.UUID
    phone: str
    name: str | None = None
    # El código de la sede, para que el front pueda comprobar que el enlace y la carta
    # que está mirando son la misma sede.
    branch_code: str | None = None


class CustomerChannelDirectory(Protocol):
    """Puerto de salida: resolver el token que viaja en el enlace de la carta."""

    async def resolve_store_token(self, token: str) -> ChannelContact | None:
        """El contacto dueño del token, o None si no existe o ya venció."""
        ...
