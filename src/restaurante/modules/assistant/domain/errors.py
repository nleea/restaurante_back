"""Los cuatro noes del asistente. Se distinguen porque el que los recibe hace cosas distintas.

Un solo "no se pudo" habría sido más corto y es exactamente el fallo: quien está delante
necesita saber si vuelve a intentar en un minuto, si tiene que comprar más, o si esto no es
para él. Los códigos viajan al front y ahí se convierten en tres frases distintas.
"""

from __future__ import annotations

from restaurante.shared.domain.errors import DomainError


class AssistantNotEntitledError(DomainError):
    """Este tenant no compró el asistente. No es un límite: es que no existe para él."""

    code = "assistant_not_entitled"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or "El asistente no está habilitado para este negocio.")


class AssistantDisabledError(DomainError):
    """El interruptor global. Es NUESTRO y no distingue tenants.

    Existe para una sola frase: "para todo ahora mismo". Por eso se evalúa antes que nada y
    por eso no se puede desactivar desde ninguna pantalla del producto.
    """

    code = "assistant_disabled"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "El asistente está temporalmente fuera de servicio."
        )


class RateLimitedError(DomainError):
    """Demasiadas llamadas por minuto. Defensivo, no comercial.

    Contesta a "¿hay algo en bucle?", no a "¿ha comprado esto?". Rechazar aquí **no consume
    cuota**: cobrarle a alguien por el mensaje que no le contestamos sería cobrarle por
    nuestra propia defensa.
    """

    code = "assistant_rate_limited"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "Demasiadas preguntas seguidas. Inténtalo en un momento."
        )


class AssistantProviderError(DomainError):
    """El proveedor falló. Lleva dentro lo que llegó a consumir.

    Los tokens viajan en la excepción porque un error a mitad de generación **ya se pagó**:
    si el fallo se propagara pelado, esa llamada no aparecería en el libro y el libro dejaría
    de cuadrar con la factura justo en los casos raros, que son los que nadie audita.
    """

    code = "assistant_provider_error"

    def __init__(
        self, detail: str, tokens_in: int = 0, tokens_out: int = 0
    ) -> None:
        super().__init__(detail)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


class QuotaExhaustedError(DomainError):
    """Se acabó lo comprado para este periodo.

    No es un error del que pregunta y por eso el asistente casi nunca lo deja salir: en la
    vía de WhatsApp se degrada a un mensaje fijo con el enlace de la carta y **sin llamar al
    modelo**. Sale tal cual sólo en el chat de administración, donde quien pregunta es
    justamente quien puede comprar más.
    """

    code = "assistant_quota_exhausted"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "Se agotó el saldo del asistente para este periodo."
        )
