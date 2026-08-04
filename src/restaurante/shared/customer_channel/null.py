"""Implementaciones nulas: el sistema exactamente como era antes de que existiera el canal.

Se eligen en la raíz de composición cuando el tenant no tiene WhatsApp emparejado o el
módulo `messaging` no está enchufado. Con ellas, un pedido se crea, se despacha y se
cancela igual que siempre y nadie recibe nada.
"""

from __future__ import annotations

import uuid

from restaurante.shared.customer_channel.ports import ChannelContact


class NullCustomerNotifier:
    """Implementa `CustomerNotifier` sin hacer nada (y sin levantar nunca)."""

    async def notify_order_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None:
        return None


class NullCustomerChannelDirectory:
    """Implementa `CustomerChannelDirectory`: ningún token resuelve."""

    async def resolve_store_token(self, token: str) -> ChannelContact | None:
        return None
