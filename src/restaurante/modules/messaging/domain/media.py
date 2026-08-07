"""Qué archivo entrante se guarda y cuál no. Decisión PURA, tomada antes de descargar.

El orden importa y es la decisión central del módulo: el sobre del webhook ya trae el tipo y el
tamaño del archivo, así que **se decide leyendo el sobre y sólo después se piden los bytes**. Un
video de 20 MB se rechaza sin que viaje. La alternativa —pedirle al puente que meta el archivo en
base64 dentro del webhook— haría que esos 20 MB llegaran siempre, a un endpoint público, para
decidir después que no los queríamos.

Qué se guarda es una lista corta a propósito. No es que el audio o la ubicación no importen: es que
hoy nada sabe leerlos, y guardar lo que nadie va a abrir es pagar almacenamiento por nada. Cuando
haya un lector, se añaden de uno en uno.

Funciones puras: sin base de datos, sin red, sin reloj. Mismo criterio que `templates.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Lo que un cliente manda de verdad y alguien va a abrir desde la bandeja.
#:
#: El PDF entra por la misma razón que ya está aceptado en el comprobante del checkout: los bancos
#: mandan el comprobante así. Dejarlo fuera sería dejar fuera el caso más común de una
#: transferencia bancaria.
STORABLE_MIMES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

#: 5 MB, el mismo número y por la misma razón que el comprobante del checkout: un comprobante es
#: una captura de pantalla, y lo que pase de aquí no es un comprobante.
MAX_MEDIA_BYTES = 5 * 1024 * 1024

#: Los tipos de mensaje que traen un archivo que podríamos querer. `sticker` no está: es un webp,
#: así que técnicamente "es una imagen", y es ruido puro.
MEDIA_MESSAGE_TYPES = frozenset({"image", "document"})


@dataclass(frozen=True)
class MediaDecision:
    """`store=False` significa "deja el marcador y no llames al puente"."""

    store: bool
    #: La extensión con la que se guardaría. Vacía cuando no se guarda.
    extension: str = ""
    #: Por qué no se guarda, para el log. Nunca se le enseña al cliente.
    reason: str = ""


def media_intent(
    message_type: str, mimetype: str | None, file_length: int | None
) -> MediaDecision:
    """¿Se baja este archivo? Se contesta con el sobre, antes de gastar un byte.

    `file_length` desconocido (el puente no siempre lo manda) **no** es motivo para rechazar: se
    baja y el tope se comprueba sobre los bytes de verdad. Rechazar por no saber el tamaño dejaría
    fuera comprobantes buenos por una omisión del proveedor.
    """
    if message_type not in MEDIA_MESSAGE_TYPES:
        return MediaDecision(False, reason=f"tipo de mensaje sin archivo ({message_type})")
    normalized = (mimetype or "").split(";")[0].strip().lower()
    extension = STORABLE_MIMES.get(normalized)
    if extension is None:
        return MediaDecision(False, reason=f"tipo de archivo no soportado ({normalized or '?'})")
    if file_length is not None and file_length > MAX_MEDIA_BYTES:
        return MediaDecision(
            False, reason=f"archivo demasiado grande ({file_length} bytes)"
        )
    return MediaDecision(True, extension=extension)


def fits(data: bytes) -> bool:
    """El tope, ya con los bytes en la mano.

    Existe además de `media_intent` porque el tamaño del sobre es una promesa del proveedor, no un
    hecho: si no lo mandó, o mintió, esto es lo que lo sostiene.
    """
    return 0 < len(data) <= MAX_MEDIA_BYTES
