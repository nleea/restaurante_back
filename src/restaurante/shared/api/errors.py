"""Traducción de errores de dominio a respuestas HTTP."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from restaurante.modules.alerts.domain.errors import AlreadyAcknowledgedError
from restaurante.modules.assistant.domain.errors import (
    AssistantDisabledError,
    AssistantNotEntitledError,
    AssistantProviderError,
    QuotaExhaustedError,
    RateLimitedError,
)
from restaurante.modules.messaging.domain.errors import (
    ContactNotReachableError,
    ConversationAlreadyClaimedError,
    MessageDeliveryError,
    SessionNotFoundError,
)
from restaurante.modules.storefront.domain.errors import OrderEditRefused
from restaurante.shared.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    BranchNotFoundError,
    CashClosedError,
    ConflictError,
    DomainError,
    InvalidTokenError,
    NotFoundError,
    TableNotFoundError,
    TenantNotResolvedError,
    ValidationError,
)

# NOTE: looked up by EXACT type below, not by isinstance — a new subclass of an
# already-mapped error still needs its own entry here or it falls through to 400.
_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    BranchNotFoundError: status.HTTP_404_NOT_FOUND,
    TableNotFoundError: status.HTTP_404_NOT_FOUND,
    TenantNotResolvedError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    CashClosedError: status.HTTP_409_CONFLICT,
    ConversationAlreadyClaimedError: status.HTTP_409_CONFLICT,
    # Misma forma que la anterior: perder la carrera por una alerta no es un fallo del
    # que la pidió, es el mundo diciendo quién la tiene. 409, y el cuerpo dice quién.
    AlreadyAcknowledgedError: status.HTTP_409_CONFLICT,
    # 409 con el motivo en el cuerpo (`refusal`): el pedido está en un estado que no admite
    # ese cambio. Entrada propia porque el mapa es por tipo EXACTO — sin ella, heredar de
    # `ConflictError` no basta y el cliente recibiría un 400 pelado.
    OrderEditRefused: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    # The outbound guard refusing is not the caller's bad input — it is the system
    # protecting the number. 409: the state of the world forbids it, retrying won't help.
    ContactNotReachableError: status.HTTP_409_CONFLICT,
    # 502: we are the proxy and the bridge behind us failed.
    MessageDeliveryError: status.HTTP_502_BAD_GATEWAY,
    # Los cuatro noes del asistente, con códigos DISTINTOS a propósito: el front tiene que
    # decir tres frases distintas —"vuelve a intentarlo", "se acabó el saldo", "esto no está
    # contratado"— y un solo 400 para las tres las haría indistinguibles.
    AssistantNotEntitledError: status.HTTP_403_FORBIDDEN,
    # 402: se acabó lo comprado. No es un fallo del que pregunta, es que hay que comprar más.
    QuotaExhaustedError: status.HTTP_402_PAYMENT_REQUIRED,
    # 429: demasiadas seguidas. Reintentar SÍ ayuda, y esa es toda la diferencia con el 402.
    RateLimitedError: status.HTTP_429_TOO_MANY_REQUESTS,
    # 503: el interruptor es nuestro y es temporal.
    AssistantDisabledError: status.HTTP_503_SERVICE_UNAVAILABLE,
    AssistantProviderError: status.HTTP_502_BAD_GATEWAY,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        http_status = _STATUS_BY_ERROR.get(
            type(exc), status.HTTP_400_BAD_REQUEST
        )
        content: dict[str, object] = {"code": exc.code, "detail": str(exc)}
        # `code` y `detail` mandan: un payload no puede pisarlos por accidente.
        for key, value in exc.payload().items():
            content.setdefault(key, value)
        return JSONResponse(status_code=http_status, content=content)
