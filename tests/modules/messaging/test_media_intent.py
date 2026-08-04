"""Qué archivo entrante se guarda, decidido con el sobre y sin descargar nada.

La prueba que importa es la de rechazar por tamaño: es lo que hace que un video de 20 MB no viaje.
Si eso se rompe, el change deja de tener la propiedad por la que se eligió pedir los bytes en vez
de recibirlos dentro del webhook.
"""

from __future__ import annotations

import pytest

from restaurante.modules.messaging.domain.media import (
    MAX_MEDIA_BYTES,
    fits,
    media_intent,
)


# --- Lo que se guarda --------------------------------------------------------
@pytest.mark.parametrize(
    ("mime", "extension"),
    [
        ("image/jpeg", ".jpg"),
        ("image/png", ".png"),
        ("image/webp", ".webp"),
    ],
)
def test_an_image_is_stored(mime: str, extension: str) -> None:
    decision = media_intent("image", mime, 1024)
    assert decision.store and decision.extension == extension


def test_a_pdf_is_stored_because_banks_send_receipts_that_way() -> None:
    decision = media_intent("document", "application/pdf", 200_000)
    assert decision.store and decision.extension == ".pdf"


def test_a_mime_with_parameters_still_matches() -> None:
    """Los proveedores mandan `image/jpeg; codecs=…` más a menudo de lo que parece."""
    assert media_intent("image", "image/jpeg; codecs=whatever", 100).store


def test_an_uppercase_mime_still_matches() -> None:
    assert media_intent("image", "IMAGE/JPEG", 100).store


# --- Lo que no se guarda -----------------------------------------------------
@pytest.mark.parametrize("kind", ["audio", "video", "sticker", "location", "text"])
def test_kinds_without_a_reader_are_left_alone(kind: str) -> None:
    """No es que no importen: es que nada sabe leerlos, y guardarlos es pagar por nada."""
    decision = media_intent(kind, "image/jpeg", 1024)
    assert not decision.store and decision.reason


def test_a_document_of_another_type_is_not_stored() -> None:
    decision = media_intent("document", "application/vnd.ms-excel", 1024)
    assert not decision.store
    assert "no soportado" in decision.reason


def test_an_oversized_file_is_refused_from_the_envelope() -> None:
    """Sin descargar: es toda la razón por la que se lee el sobre primero."""
    decision = media_intent("video", "video/mp4", 20 * 1024 * 1024)
    assert not decision.store

    huge_image = media_intent("image", "image/jpeg", MAX_MEDIA_BYTES + 1)
    assert not huge_image.store
    assert "demasiado grande" in huge_image.reason


def test_exactly_at_the_limit_is_stored() -> None:
    assert media_intent("image", "image/jpeg", MAX_MEDIA_BYTES).store


def test_a_missing_size_is_not_a_refusal() -> None:
    """El puente no siempre manda el tamaño; rechazar por su omisión perdería comprobantes.

    El tope se comprueba entonces sobre los bytes de verdad (`fits`).
    """
    assert media_intent("image", "image/jpeg", None).store


def test_a_missing_mime_is_a_refusal() -> None:
    """Sin tipo no se puede ni elegir la extensión ni saber si es un PDF."""
    assert not media_intent("image", None, 1024).store


# --- El tope, ya con los bytes en la mano ------------------------------------
def test_fits_guards_what_the_envelope_promised() -> None:
    """El tamaño del sobre es una promesa del proveedor, no un hecho."""
    assert fits(b"x" * 10)
    assert fits(b"x" * MAX_MEDIA_BYTES)
    assert not fits(b"x" * (MAX_MEDIA_BYTES + 1))
    assert not fits(b"")
