"""Un teléfono tecleado por una persona y uno que vino de WhatsApp son el mismo número.

Este fichero existe por un fallo que NO da error: el escalado de alertas no llegaba porque
`+57 300 111 2233` (lo que alguien escribe en Personal) no es igual, como texto, a
`573001112233` (lo que WhatsApp manda en el JID). El guardián lo leía como "no contactable",
lo anotaba en un log del servidor, y desde fuera sólo se veía que el aviso nunca salió.
"""

from __future__ import annotations

import pytest

from restaurante.shared.domain.phones import normalize_phone


@pytest.mark.parametrize(
    "written",
    [
        "+573001112233",
        "573001112233",
        "+57 300 111 2233",
        "+57 (300) 111-2233",
        "300 111 2233 ",
        "\t+57-300-111-2233\n",
    ],
)
def test_however_a_person_writes_it_it_ends_up_the_same(written: str) -> None:
    # Todas estas formas salen de la misma cabeza y del mismo número.
    assert normalize_phone(written).endswith("3001112233")


def test_the_form_whatsapp_sends_is_left_alone() -> None:
    """Lo que llega del JID ya es canónico: normalizarlo no puede cambiarlo."""
    assert normalize_phone("573001112233") == "573001112233"


def test_two_ways_of_writing_the_same_number_now_match() -> None:
    # Es literalmente la comparación que hace `is_reachable`.
    assert normalize_phone("+57 300 111 2233") == normalize_phone("573001112233")


def test_a_privacy_jid_is_never_touched() -> None:
    """`@lid` NO es un teléfono: es lo único con lo que se le puede escribir a ese contacto.

    Quitarle los símbolos dejaría una cifra sin sentido, y Evolution le pegaría
    `@s.whatsapp.net` al enviar — apuntando a un usuario que no existe.
    """
    assert normalize_phone("209876543210987@lid") == "209876543210987@lid"
    assert normalize_phone("  123@lid  ") == "123@lid"


def test_an_empty_or_junk_value_becomes_empty_rather_than_wrong() -> None:
    # Vacío es honesto: "no hay teléfono". Inventar dígitos sería peor.
    assert normalize_phone("") == ""
    assert normalize_phone("   ") == ""
    assert normalize_phone("sin teléfono") == ""
