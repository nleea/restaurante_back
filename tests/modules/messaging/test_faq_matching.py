"""El matching de las FAQs. Sin base, sin app, sin reloj.

Esta suite es la que sostiene el change entero: el módulo rechazó por escrito construir un bot de
palabras clave ("una fábrica de bugs"), y lo que separa esto de aquello son dos cosas — el límite
de palabra, que se prueba aquí, y los dos gates, que se prueban en `test_faq_replies.py`.

Las cuatro primeras pruebas son la tabla de falsos positivos del diseño, una por fila, con el
mensaje real que un cliente escribe. Si alguna se cae, el change ha dejado de ser defendible.
"""

from __future__ import annotations

import pytest

from restaurante.modules.messaging.domain.entities import FaqEntry
from restaurante.modules.messaging.domain.faq import (
    asks_for_a_person,
    first_match,
    matches,
    normalize,
    plural_variants,
    reserved_words_in,
)


def _faq(faq_id: str, *triggers: str, enabled: bool = True, text: str = "ok") -> FaqEntry:
    return FaqEntry(
        id=faq_id, name=faq_id, triggers=list(triggers), text=text, enabled=enabled
    )


# --- La tabla de falsos positivos --------------------------------------------
def test_a_complaint_about_a_payment_does_not_trigger_the_payment_faq() -> None:
    """"ya pagué" NO es "pago". Es el falso positivo con peor cara del conjunto."""
    assert not matches("pago", "ya pagué y no me llegó")


def test_asking_where_an_order_is_does_not_trigger_the_delivery_faq() -> None:
    """"¿ya me lo enviaron?" pregunta por SU pedido, no por la cobertura."""
    assert not matches("envian", "¿ya me lo enviaron?")
    assert not matches("envios", "¿ya me lo enviaron?")


def test_a_plural_question_finds_a_singular_trigger() -> None:
    """El precipicio que evita la variante de plural: `domicilio` ≠ `domicilios`."""
    assert matches("domicilio", "¿hacen domicilios?")


def test_the_customer_giving_their_own_address_still_matches() -> None:
    """Se documenta el residuo, no se disimula.

    Palabra completa NO salva este caso: `direccion` es palabra completa ahí. Lo que lo salva es
    el gate de pedido vivo, y por eso el gate no es opcional. Esta prueba existe para que nadie
    "arregle" el matching creyendo que aquí falta algo.
    """
    assert matches("direccion", "mi dirección es la calle 5 #3-20")


# --- Normalización -----------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("¿A QUÉ HORA ABREN?", "a que hora abren"),
        ("Ubicación...", "ubicacion"),
        ("  dónde   están  ", "donde estan"),
        ("mañana", "manana"),
        ("Aceptan Tarjeta?!", "aceptan tarjeta"),
    ],
)
def test_normalization_is_predictable(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_both_sides_get_the_same_treatment() -> None:
    """Que `mañana` acabe en `manana` da igual: el gatillo también."""
    assert matches("mañana", "¿abren mañana?")


# --- Palabra completa --------------------------------------------------------
@pytest.mark.parametrize(
    ("trigger", "message"),
    [
        ("pago", "pagoteca"),
        ("hora", "ahora mismo"),
        ("envio", "reenvio"),
    ],
)
def test_a_trigger_inside_another_word_does_not_match(
    trigger: str, message: str
) -> None:
    assert not matches(trigger, message)


def test_a_phrase_matches_as_a_whole_phrase() -> None:
    assert matches("a que hora abren", "buenas, ¿a qué hora abren hoy?")
    # Las mismas palabras en otro orden no son la frase.
    assert not matches("a que hora abren", "abren a que hora dijiste")


def test_an_empty_trigger_never_matches() -> None:
    assert not matches("", "cualquier cosa")
    assert not matches("   ", "cualquier cosa")


# --- Plural, y sólo plural ---------------------------------------------------
@pytest.mark.parametrize(
    ("trigger", "expected_subset"),
    [
        ("domicilio", {"domicilio", "domicilios"}),
        ("horarios", {"horarios", "horario"}),
        ("pago", {"pago", "pagos"}),
    ],
)
def test_plural_variants(trigger: str, expected_subset: set[str]) -> None:
    assert expected_subset <= plural_variants(trigger)


def test_no_stemming_beyond_the_plural() -> None:
    """Recortar sufijos genéricos devolvería el bug de "ya pagué"."""
    assert "pagu" not in plural_variants("pago")
    assert "pagué" not in plural_variants("pago")
    assert not matches("pago", "pagué")
    assert not matches("cerrar", "cerrado")


# --- Prioridad ---------------------------------------------------------------
def test_the_first_matching_faq_wins() -> None:
    faqs = [_faq("horario", "horario"), _faq("general", "horario", "carta")]
    assert (first_match(faqs, "¿cuál es el horario?") or _faq("x")).id == "horario"


def test_reordering_changes_the_winner() -> None:
    """El orden ES la prioridad: es lo que las flechas de la pantalla mueven."""
    a, b = _faq("a", "horario"), _faq("b", "horario")
    assert (first_match([a, b], "horario") or _faq("x")).id == "a"
    assert (first_match([b, a], "horario") or _faq("x")).id == "b"


def test_a_disabled_faq_never_wins() -> None:
    faqs = [_faq("apagada", "horario", enabled=False), _faq("encendida", "horario")]
    assert (first_match(faqs, "horario") or _faq("x")).id == "encendida"


def test_a_faq_without_text_is_skipped() -> None:
    """Defensa en profundidad: la validación lo impide al guardar, pero mandar un mensaje
    vacío es peor que no contestar."""
    faqs = [_faq("vacia", "horario", text="  "), _faq("buena", "horario")]
    assert (first_match(faqs, "horario") or _faq("x")).id == "buena"


def test_no_match_is_silence() -> None:
    assert first_match([_faq("horario", "horario")], "quiero una hamburguesa") is None


# --- Vocabulario reservado ---------------------------------------------------
@pytest.mark.parametrize(
    "trigger", ["asistente", "bot", "1", "humano", "cancelar", "reembolso"]
)
def test_a_reserved_word_is_reported(trigger: str) -> None:
    assert reserved_words_in(trigger)


def test_containment_catches_the_dead_end_trigger() -> None:
    """`cancelaciones` pasaría una comprobación por igualdad y no dispararía nunca.

    Es el callejón sin salida que la validación por contención existe para evitar: la FAQ queda
    encendida en la pantalla y el mensaje que la activaría se va a una persona antes.
    """
    assert "cancela" in reserved_words_in("cancelaciones")
    assert asks_for_a_person("¿cómo hago una cancelación?")


def test_an_ordinary_trigger_is_not_reserved() -> None:
    for trigger in ("horario", "domicilio", "metodos de pago", "donde estan"):
        assert reserved_words_in(trigger) == []


def test_asking_for_a_person_is_detected() -> None:
    for message in (
        "quiero hablar con una persona",
        "¿hay alguien?",
        "necesito un asesor",
        "quiero cancelar mi pedido",
        "¿me pueden hacer una devolución?",
    ):
        assert asks_for_a_person(message)


def test_the_opt_in_digit_does_not_silence_every_faq() -> None:
    """`1` está prohibido como gatillo, pero no puede callar a las FAQs.

    Como subcadena aparece en "quiero 1 hamburguesa" y en media dirección de Riohacha; si entrara
    en el gate, las FAQs no contestarían casi nunca.
    """
    assert not asks_for_a_person("quiero 1 hamburguesa")
    assert not asks_for_a_person("calle 1 con carrera 15")
