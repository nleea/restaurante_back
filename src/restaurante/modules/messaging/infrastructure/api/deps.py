"""Dependency wiring for the messaging API — and the composition root of the gateway.

The single most important line in this module is in `get_whatsapp_gateway`: it returns
the **guarded** gateway and nothing else ever hands out the raw bridge adapter. That is
what makes "we never message someone who did not write first" a property of the system
rather than a rule callers must remember.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.messaging.application.use_cases.autoreply import (
    AutoreplyService,
)
from restaurante.modules.messaging.application.use_cases.manage_messaging import (
    MessagingService,
)
from restaurante.modules.messaging.domain.ports import (
    MessagingRepository,
    WhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.messaging.infrastructure.whatsapp.bridge import (
    BridgeWhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.whatsapp.guard import (
    GuardedWhatsAppGateway,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session
from restaurante.shared.realtime.deps import get_event_publisher
from restaurante.shared.storage.deps import build_object_storage

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def build_whatsapp_gateway(repo: MessagingRepository) -> WhatsAppGateway:
    """The ONLY sanctioned way to obtain a gateway.

    Always returns the guard wrapping the bridge. If you ever find yourself wanting the
    bare `BridgeWhatsAppGateway` outside a test, the requirement is wrong, not the guard.
    """
    settings = get_settings()
    bridge = BridgeWhatsAppGateway(
        base_url=settings.whatsapp_bridge_base_url,
        api_key=settings.whatsapp_bridge_api_key,
        timeout_seconds=settings.whatsapp_bridge_timeout_seconds,
    )
    return GuardedWhatsAppGateway(bridge, repo)


def build_customer_channel(session: AsyncSession) -> AutoreplyService:
    """El canal del cliente sobre la sesión dada, para los OTROS módulos.

    `AutoreplyService` cumple los dos puertos de `shared/customer_channel` sin heredar de
    nada: pedidos y domicilios enchufan esto y siguen sin conocer WhatsApp. Sobre la MISMA
    sesión que la transición que lo dispara, para que el aviso vea el pedido ya escrito.
    """
    repo = SqlAlchemyMessagingRepository(session)
    return AutoreplyService(
        repo=repo,
        # Siempre el gateway GUARDADO: un aviso de estado tampoco puede iniciar una charla.
        gateway=build_whatsapp_gateway(repo),
        storefront_base_url=get_settings().storefront_base_url,
    )


def _assistant_responder(
    session: AsyncSession, autoreply: AutoreplyService, gateway: WhatsAppGateway
) -> Any:
    """El asistente, importado AQUÍ DENTRO y no arriba, a propósito.

    El ciclo es real y es inherente a una raíz de composición: messaging compone el
    asistente, y el asistente compone servicios (carta, pedidos) que a su vez componen
    messaging. Romperlo con un import diferido es más honesto que inventar un módulo
    intermedio cuyo único trabajo sería existir para que los imports salgan.

    Messaging sigue sin conocer al asistente en ninguna FIRMA: lo que declara es su propio
    `Protocol` local, y esto sólo elige qué objeto lo cumple.
    """
    from restaurante.modules.assistant.infrastructure.whatsapp_responder import (
        WhatsAppAssistantResponder,
    )

    return WhatsAppAssistantResponder(session, autoreply, gateway)


def _payment_claims(session: AsyncSession) -> Any:
    """El servicio de pagos de `orders`, que cumple el `PaymentClaimRecorder` local.

    Cumple el puerto sin heredar de nada y sin saber que existe: tiene el método con esa forma
    porque es su propio caso de uso público. Messaging sigue sin importar `orders` en ninguna firma.
    """
    from restaurante.modules.orders.infrastructure.api.deps import get_payment_service

    return get_payment_service(session)


def get_messaging_service(session: SessionDep) -> MessagingService:
    settings = get_settings()
    repo = SqlAlchemyMessagingRepository(session)
    gateway = build_whatsapp_gateway(repo)
    autoreply = AutoreplyService(
        repo=repo,
        gateway=gateway,
        storefront_base_url=settings.storefront_base_url,
    )
    return MessagingService(
        repo=repo,
        gateway=gateway,
        events=get_event_publisher(),
        idle_hours=settings.whatsapp_conversation_idle_hours,
        public_base_url=settings.whatsapp_public_base_url,
        webhook_secret=settings.whatsapp_webhook_secret,
        # El saludo sale por el MISMO gateway guardado: no puede iniciar una conversación.
        autoreply=autoreply,
        # El asistente, si el módulo está desplegado. Ausente → ninguna conversación entra
        # en modo bot y todas las atiende una persona, como antes de la fase 4.
        assistant=_assistant_responder(session, autoreply, gateway),
        # Para guardar los archivos que llegan. Sin R2 configurado, `is_configured` es falso y
        # un archivo entrante deja su marcador — el comportamiento de antes de soportarlos.
        media_storage=build_object_storage(),
        # Quien registra la declaración de pago cuando el comprobante llegó por el chat. Import
        # diferido por lo mismo que el asistente: la raíz de composición sí puede conocer a los
        # dos módulos, las FIRMAS de messaging no.
        claims=_payment_claims(session),
    )


MessagingServiceDep = Annotated[MessagingService, Depends(get_messaging_service)]
