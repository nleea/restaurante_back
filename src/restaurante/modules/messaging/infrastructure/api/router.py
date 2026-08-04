"""Messaging API: the shared WhatsApp inbox, per-branch sessions, and the webhook.

Two routers with deliberately different authentication:

- `router` — the staff-facing inbox and sessions. Reads need `messaging.read`, acting
  on a conversation needs `messaging.attend`, pairing needs `messaging.manage`.
- `webhook_router` — the bridge's inbound callback. No user, no tenant subdomain: it
  authenticates with a shared secret and derives the tenant from the session matching
  the instance reference in the path.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from restaurante.modules.identity.infrastructure.api.deps import (
    CurrentUserDep,
    require_permission,
)
from restaurante.modules.messaging.application.use_cases.autoreply import (
    DEFAULT_STATUS_MAPPING,
    SUGGESTED_FAQS,
    assistant_available,
    order_number,
)
from restaurante.modules.messaging.application.use_cases.manage_messaging import (
    INBOX_TOPIC,
)
from restaurante.modules.messaging.domain.errors import SessionNotFoundError
from restaurante.modules.messaging.domain.quick_reply import SUGGESTED_QUICK_REPLIES
from restaurante.modules.messaging.domain.templates import (
    AWAITING_PAYMENT_PLACEHOLDERS,
    FAQ_PLACEHOLDERS,
    GREETING_PLACEHOLDERS,
    ORDER_PLACEHOLDERS,
)
from restaurante.modules.messaging.infrastructure.api.deps import (
    MessagingServiceDep,
    TenantDep,
)
from restaurante.modules.messaging.infrastructure.api.schemas import (
    AutoreplyDefaultsResponse,
    AutoreplySettingsSchema,
    ConversationResponse,
    CreateSessionRequest,
    EligibleOrderResponse,
    FaqSchema,
    MenuLinkResponse,
    PairingResponse,
    QuickRepliesResponse,
    QuickReplySchema,
    ReplyRequest,
    SessionResponse,
    SessionStatusRequest,
    StatusMessageSchema,
    ThreadResponse,
    UseAsProofRequest,
    WebhookAck,
    WebhookMessagePayload,
    connection_update,
    delivery_update,
    session_response,
)
from restaurante.shared.config import get_settings
from restaurante.shared.realtime.deps import EventStreamDep, event_stream_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["messaging"])
webhook_router = APIRouter(prefix="/webhooks", tags=["messaging"])

_READ = Depends(require_permission("messaging.read"))
_ATTEND = Depends(require_permission("messaging.attend"))
_MANAGE = Depends(require_permission("messaging.manage"))
# Pegar un comprobante a un pedido es dinero, no atención: se pide el permiso de cobrar.
_PAY = Depends(require_permission("orders.pay"))

BranchQuery = Annotated[uuid.UUID, Query(description="Sucursal activa del inbox.")]


# --- Inbox ------------------------------------------------------------------
@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    dependencies=[_READ],
)
async def list_conversations(
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
    include_closed: bool = False,
) -> list[ConversationResponse]:
    summaries = await service.list_conversations(
        tenant_id, branch_id, include_closed=include_closed
    )
    return [ConversationResponse.from_summary(s) for s in summaries]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ThreadResponse,
    dependencies=[_READ],
)
async def get_thread(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> ThreadResponse:
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return ThreadResponse.from_thread(thread)


@router.post(
    "/conversations/{conversation_id}/claim",
    response_model=ThreadResponse,
    dependencies=[_ATTEND],
)
async def claim_conversation(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
    current_user: CurrentUserDep,
) -> ThreadResponse:
    employee_id = await service.resolve_acting_employee(
        tenant_id, current_user.id, branch_id
    )
    await service.claim(tenant_id, branch_id, conversation_id, employee_id)
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return ThreadResponse.from_thread(thread)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_ATTEND],
)
async def send_reply(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    payload: ReplyRequest,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
    current_user: CurrentUserDep,
) -> ThreadResponse:
    employee_id = await service.resolve_acting_employee(
        tenant_id, current_user.id, branch_id
    )
    await service.send_reply(
        tenant_id, branch_id, conversation_id, employee_id, payload.body
    )
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return ThreadResponse.from_thread(thread)


@router.post(
    "/conversations/{conversation_id}/media",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_ATTEND],
)
async def send_media_reply(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
    current_user: CurrentUserDep,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form()] = "",
) -> ThreadResponse:
    """Manda un archivo por el chat. Los bytes pasan por el API, no por una URL prefirmada.

    Misma postura que el comprobante del checkout: una firma autoriza un PUT pero **no acota
    cuántos bytes se meten**, y aquí además el archivo hay que tenerlo en memoria de todas formas
    para entregárselo al puente.
    """
    employee_id = await service.resolve_acting_employee(
        tenant_id, current_user.id, branch_id
    )
    await service.send_media_reply(
        tenant_id,
        branch_id,
        conversation_id,
        employee_id,
        await file.read(),
        mimetype=file.content_type or "",
        filename=file.filename or "archivo",
        caption=caption,
    )
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return ThreadResponse.from_thread(thread)


@router.post(
    "/conversations/{conversation_id}/menu-link",
    response_model=MenuLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_ATTEND],
)
async def send_menu_link(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
    current_user: CurrentUserDep,
) -> MenuLinkResponse:
    """Manda el enlace a la carta de ESTA sede, con su token, firmado por el agente.

    Es `messaging.attend` y no `manage`: quien atiende el chat es quien decide mandar la
    carta, igual que decide qué responder.
    """
    employee_id = await service.resolve_acting_employee(
        tenant_id, current_user.id, branch_id
    )
    link = await service.send_menu_link(
        tenant_id, branch_id, conversation_id, employee_id
    )
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return MenuLinkResponse(link=link, thread=ThreadResponse.from_thread(thread))


# --- Un comprobante que nace del chat ---------------------------------------
@router.get(
    "/conversations/{conversation_id}/eligible-orders",
    response_model=list[EligibleOrderResponse],
    dependencies=[_PAY],
)
async def eligible_orders_for_proof(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> list[EligibleOrderResponse]:
    """A qué pedidos de este contacto se les puede pegar un comprobante.

    Es `orders.pay` y no `messaging.attend`: enseña saldos de pedidos, y quien no puede cobrar no
    tiene por qué verlos.
    """
    orders = await service.eligible_orders_for_proof(
        tenant_id, branch_id, conversation_id
    )
    return [
        EligibleOrderResponse(
            order_id=o.order_id,
            number=order_number(o.order_id),
            total=o.total,
            balance=o.balance,
        )
        for o in orders
    ]


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/use-as-proof",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_PAY],
)
async def use_message_as_proof(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    branch_id: BranchQuery,
    payload: UseAsProofRequest,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> Response:
    """Usa el archivo de un mensaje como comprobante de un pedido de ese contacto.

    **`orders.pay`, no `messaging.attend`**: crear un claim es un paso del camino del dinero. Que
    en el piloto sea la misma persona quien atiende el chat y quien cobra es una realidad, no una
    excusa para mezclar los dos permisos.
    """
    await service.use_message_as_proof(
        tenant_id,
        branch_id,
        conversation_id,
        message_id,
        payload.order_id,
        payload.amount,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Autoreply settings -----------------------------------------------------
@router.get("/autoreply", response_model=AutoreplyDefaultsResponse, dependencies=[_MANAGE])
async def get_autoreply_settings(
    service: MessagingServiceDep, tenant_id: TenantDep
) -> AutoreplyDefaultsResponse:
    """Los ajustes vigentes, más los valores de fábrica y los marcadores válidos.

    Todo junto en una respuesta porque la pantalla los necesita a la vez: sin el mapeo de
    fábrica no puede ofrecer "restaurar", y sin la lista de marcadores el dueño escribe
    `{cliente}` y descubre el error al guardar.
    """
    settings = await service.autoreply_settings(tenant_id)
    return AutoreplyDefaultsResponse(
        settings=AutoreplySettingsSchema.from_settings(settings),
        default_status_mapping={
            state: StatusMessageSchema(
                enabled=bool(entry.get("enabled", False)),
                text=str(entry.get("text") or ""),
            )
            for state, entry in DEFAULT_STATUS_MAPPING.items()
        },
        suggested_faqs=[FaqSchema.from_entry(faq) for faq in SUGGESTED_FAQS],
        suggested_quick_replies=[
            QuickReplySchema.from_entry(entry) for entry in SUGGESTED_QUICK_REPLIES
        ],
        greeting_placeholders=sorted(GREETING_PLACEHOLDERS),
        order_placeholders=sorted(ORDER_PLACEHOLDERS),
        faq_placeholders=sorted(FAQ_PLACEHOLDERS),
        awaiting_payment_placeholders=sorted(AWAITING_PAYMENT_PLACEHOLDERS),
        assistant_available=assistant_available(),
    )


@router.put("/autoreply", response_model=AutoreplySettingsSchema, dependencies=[_MANAGE])
async def save_autoreply_settings(
    payload: AutoreplySettingsSchema,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> AutoreplySettingsSchema:
    """Guarda los ajustes. Un marcador desconocido es 422 nombrándolo, no un envío roto."""
    saved = await service.save_autoreply_settings(payload.to_settings(tenant_id))
    return AutoreplySettingsSchema.from_settings(saved)


@router.get(
    "/quick-replies", response_model=QuickRepliesResponse, dependencies=[_ATTEND]
)
async def get_quick_replies(
    service: MessagingServiceDep, tenant_id: TenantDep
) -> QuickRepliesResponse:
    """Las plantillas del tenant, para el compositor del inbox.

    **`messaging.attend` y no `manage`**, y por eso existe este endpoint en vez de leerlas del
    `GET /autoreply`: ése devuelve el saludo, el mapeo de estados y las FAQs, y está detrás de
    `manage`. Quien atiende el chat en hora punta no administra nada, así que por esa puerta la
    feature la usaría sólo el dueño —justo quien no está en el chat—. Aquí sale la lista y nada
    más, así que abrirla a `attend` no enseña ningún otro ajuste.

    Tampoco es `messaging.read`: la lista sólo existe para meterla en una respuesta, y quien no
    puede responder no tiene nada que hacer con ella.

    Devuelve **lo guardado**, nunca las sugeridas. Ver `quick_replies_for`.
    """
    entries = await service.quick_replies(tenant_id)
    return QuickRepliesResponse(
        quick_replies=[QuickReplySchema.from_entry(entry) for entry in entries]
    )


@router.post(
    "/conversations/{conversation_id}/close",
    response_model=ThreadResponse,
    dependencies=[_ATTEND],
)
async def close_conversation(
    conversation_id: uuid.UUID,
    branch_id: BranchQuery,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> ThreadResponse:
    await service.close(tenant_id, branch_id, conversation_id)
    thread = await service.get_thread(tenant_id, branch_id, conversation_id)
    return ThreadResponse.from_thread(thread)


@router.get("/events", dependencies=[_READ])
async def stream_inbox_events(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """SSE doorbell for the branch's inbox (heartbeat every ~15 s).

    Frames are hints, not payloads: on receipt the inbox refetches. Degrades to
    heartbeats when the broker is down, so the client keeps the connection and relies
    on its polling cadence for freshness.
    """
    return event_stream_response(stream, INBOX_TOPIC, tenant_id, branch_id)


# --- Sessions ---------------------------------------------------------------
@router.get("/sessions", response_model=list[SessionResponse], dependencies=[_MANAGE])
async def list_sessions(
    service: MessagingServiceDep, tenant_id: TenantDep
) -> list[SessionResponse]:
    return [session_response(s) for s in await service.list_sessions(tenant_id)]


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
)
async def create_session(
    payload: CreateSessionRequest,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> SessionResponse:
    session = await service.create_session(
        tenant_id, payload.branch_id, payload.provider_instance_ref
    )
    return session_response(session)


@router.post(
    "/sessions/{session_id}/pair",
    response_model=PairingResponse,
    dependencies=[_MANAGE],
)
async def start_pairing(
    session_id: uuid.UUID, service: MessagingServiceDep, tenant_id: TenantDep
) -> PairingResponse:
    """Prepara la instancia en el puente, registra el webhook y devuelve el QR.

    Registrar el webhook es parte de emparejar y no un paso aparte: un número emparejado sin
    webhook recibe mensajes que no llegan a ninguna parte.
    """
    session, qr = await service.start_pairing(tenant_id, session_id)
    return PairingResponse(session=session_response(session), qr=qr)


@router.patch(
    "/sessions/{session_id}/status",
    response_model=SessionResponse,
    dependencies=[_MANAGE],
)
async def update_session_status(
    session_id: uuid.UUID,
    payload: SessionStatusRequest,
    service: MessagingServiceDep,
    tenant_id: TenantDep,
) -> SessionResponse:
    session = await service.apply_status_update(
        tenant_id,
        session_id,
        status=payload.status,
        phone_number=payload.phone_number,
    )
    return session_response(session)


# --- Inbound webhook --------------------------------------------------------
@webhook_router.post("/whatsapp/{instance_ref}", response_model=WebhookAck)
async def whatsapp_webhook(
    instance_ref: str,
    service: MessagingServiceDep,
    payload: Annotated[WebhookMessagePayload, Body()],
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> WebhookAck:
    """Inbound notifications from the bridge.

    Every outcome the bridge could retry on answers 200: a duplicate, an unparseable
    payload, an unknown instance. A 4xx here means the bridge redelivers forever, and
    the one thing worse than dropping a malformed payload is a retry storm.

    A wrong or missing secret is the exception — that is answered 401 and persists
    nothing, because it is not the real bridge asking.
    """
    settings = get_settings()
    if not _secret_ok(x_webhook_secret, settings.whatsapp_webhook_secret):
        logger.warning(
            "Rejected WhatsApp webhook with a bad secret (instance=%s)", instance_ref
        )
        # Raised, not returned: nothing must be persisted on this path.
        from restaurante.shared.domain.errors import AuthenticationError

        raise AuthenticationError("Secreto de webhook inválido.")

    # Un cambio de estado del número. Se atiende ANTES de intentar leerlo como mensaje,
    # porque no lo es — y sin esto el estado de la sesión no se actualizaba nunca: se
    # quedaba en `qr_pending` desde que se pidió el QR aunque el número llevara días
    # recibiendo, lo que además hacía que la regla "el WhatsApp dejó de recibir" avisara en
    # falso sobre una sucursal perfectamente sana.
    update = connection_update(payload)
    if update is not None:
        try:
            await service.apply_status_by_instance(
                instance_ref, status=update.status, phone_number=update.phone_number
            )
        except SessionNotFoundError:
            logger.warning("Estado de una instancia desconocida: %s", instance_ref)
            return WebhookAck(status="ignored", detail="instancia desconocida")
        return WebhookAck(status="ok", detail=f"estado: {update.status}")

    # Un acuse de entrega (✓✓). Se atiende ANTES de leer el sobre como mensaje entrante, por lo
    # mismo que el cambio de estado: no lo es. Hoy `to_inbound` ya devolvería `None` para un
    # `messages.update` —filtra por el nombre del evento—, así que el orden es defensa en
    # profundidad; lo que sí cambia es que la respuesta diga la verdad ("acuse") en vez de
    # "payload sin id o remitente", que es lo que se lee al depurar el webhook a las once.
    report = delivery_update(payload)
    if report is not None:
        changed = await service.apply_delivery_report(
            instance_ref,
            provider_message_id=report.provider_message_id,
            state=report.state,
        )
        # Sin warning cuando no cambia nada, y es deliberado: el puente reporta también lo que el
        # dueño escribe desde su propio teléfono. Un log por cada uno convierte el registro en
        # ruido el primer día que alguien conteste desde el móvil.
        return WebhookAck(status="receipt" if changed else "ignored")

    inbound = payload.to_inbound(instance_ref)
    if inbound is None:
        logger.warning("Unusable WhatsApp payload for instance %s", instance_ref)
        return WebhookAck(status="ignored", detail="payload sin id o remitente")

    try:
        message = await service.handle_inbound(inbound)
    except SessionNotFoundError:
        logger.warning("WhatsApp webhook for unknown instance %s", instance_ref)
        return WebhookAck(status="ignored", detail="instancia desconocida")

    if message is None:
        return WebhookAck(status="duplicate")
    return WebhookAck(status="stored")


def _secret_ok(provided: str | None, expected: str) -> bool:
    """Constant-time compare. An empty configured secret refuses everything.

    An unconfigured secret must fail closed: this endpoint has no user behind it, so
    "no secret set" cannot mean "anyone may post messages into the inbox".
    """
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)
