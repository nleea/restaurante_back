"""Las respuestas rápidas, sin levantar la app.

Funciones puras: sin base, sin red, sin reloj. Lo que se prueba aquí es lo único que el backend
promete sobre las plantillas —que no se pueda guardar una que se vería rota en el chat— porque
todo lo demás (cuándo se envía, a quién) lo decide una persona y no hay código que probar.
"""

from __future__ import annotations

import pytest

from restaurante.modules.messaging.domain.entities import QuickReply
from restaurante.modules.messaging.domain.quick_reply import (
    MAX_QUICK_REPLIES,
    MAX_QUICK_REPLY_CHARS,
    MAX_QUICK_REPLY_NAME_CHARS,
    SUGGESTED_QUICK_REPLIES,
    validate_quick_replies,
)
from restaurante.shared.domain.errors import ValidationError


def entry(**overrides: object) -> QuickReply:
    values: dict[str, object] = {
        "id": "quick-1",
        "name": "Va en camino",
        "text": "Tu pedido ya salió.",
    }
    values.update(overrides)
    return QuickReply(**values)  # type: ignore[arg-type]


class TestValidEntries:
    def test_a_plain_entry_passes(self) -> None:
        validate_quick_replies([entry()])

    def test_an_empty_list_is_valid(self) -> None:
        """`[]` es una decisión legítima del dueño: "ninguna". No es un error."""
        validate_quick_replies([])

    def test_the_maximum_number_of_entries_is_allowed(self) -> None:
        validate_quick_replies(
            [entry(id=f"quick-{i}") for i in range(MAX_QUICK_REPLIES)]
        )

    def test_suggested_entries_pass_their_own_validation(self) -> None:
        """Una sugerida inválida es un botón que rompe la pantalla del dueño."""
        validate_quick_replies(list(SUGGESTED_QUICK_REPLIES))

    def test_suggested_entries_have_unique_ids(self) -> None:
        ids = [item.id for item in SUGGESTED_QUICK_REPLIES]
        assert len(ids) == len(set(ids))


class TestRejectedEntries:
    def test_missing_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="identificador"):
            validate_quick_replies([entry(id="  ")])

    def test_duplicate_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="repetido"):
            validate_quick_replies([entry(), entry(name="Otra")])

    def test_missing_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nombre"):
            validate_quick_replies([entry(name="   ")])

    def test_blank_text_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="texto"):
            validate_quick_replies([entry(text="   ")])

    def test_over_long_text_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=str(MAX_QUICK_REPLY_CHARS)):
            validate_quick_replies([entry(text="x" * (MAX_QUICK_REPLY_CHARS + 1))])

    def test_over_long_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=str(MAX_QUICK_REPLY_NAME_CHARS)):
            validate_quick_replies([entry(name="x" * (MAX_QUICK_REPLY_NAME_CHARS + 1))])

    def test_too_many_entries_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Demasiadas"):
            validate_quick_replies(
                [entry(id=f"quick-{i}") for i in range(MAX_QUICK_REPLIES + 1)]
            )

    def test_the_error_names_the_offending_entry(self) -> None:
        """Con veinte tarjetas en pantalla, "datos inválidos" no le sirve a nadie."""
        with pytest.raises(ValidationError, match="Datos de Nequi"):
            validate_quick_replies([entry(name="Datos de Nequi", text="")])

    def test_an_unnamed_entry_is_located_by_position(self) -> None:
        with pytest.raises(ValidationError, match="#2"):
            validate_quick_replies([entry(), entry(id="quick-2", name="")])


class TestPlaceholders:
    """El compositor no interpola, así que un marcador guardado saldría con las llaves puestas."""

    def test_a_real_autoreply_marker_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"\{menu_link\}"):
            validate_quick_replies([entry(text="Pide aquí: {menu_link}")])

    def test_an_invented_marker_is_rejected_too(self) -> None:
        """El rechazo no depende de que el marcador exista: depende de que nadie lo resuelva."""
        with pytest.raises(ValidationError, match=r"\{nombre\}"):
            validate_quick_replies([entry(text="Hola {nombre}, tu pedido salió.")])

    def test_the_error_explains_why(self) -> None:
        with pytest.raises(ValidationError, match="no rellenan marcadores"):
            validate_quick_replies([entry(text="{hours_line}")])

    def test_braces_without_a_marker_shape_are_left_alone(self) -> None:
        """`{` suelto no es un marcador. Rechazarlo sería prohibir escribir emoticonos raros."""
        validate_quick_replies([entry(text="Combo {2 x 1} de hoy :)")])
