"""Errores del módulo de alertas."""

from __future__ import annotations

from restaurante.shared.domain.errors import ConflictError


class AlreadyAcknowledgedError(ConflictError):
    """Otra persona la tomó primero.

    Perder la carrera es información, no un fallo: lo útil es decir quién la tiene, para que
    el segundo no repita el trabajo. Es la misma forma que la toma de una conversación en el
    inbox compartido.
    """

    def __init__(self, holder_name: str | None) -> None:
        who = holder_name or "otra persona"
        super().__init__(f"Esta alerta ya la tomó {who}.")
        self.holder_name = holder_name
