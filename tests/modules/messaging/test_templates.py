"""Interpolación de marcadores: pura, sin motor de plantillas."""

from __future__ import annotations

from restaurante.modules.messaging.domain.templates import (
    FAQ_PLACEHOLDERS,
    GREETING_PLACEHOLDERS,
    find_placeholders,
    format_hours_line,
    format_next_opening,
    render,
    unknown_placeholders,
)


def test_renders_the_placeholders_it_knows() -> None:
    text = "Hola, somos {branch_name}. Mira la carta: {menu_link}"
    out = render(text, {"branch_name": "Sede Centro", "menu_link": "https://x/store/centro"})
    assert out == "Hola, somos Sede Centro. Mira la carta: https://x/store/centro"


def test_a_placeholder_without_value_stays_visible() -> None:
    """Feo pero honesto: un hueco vacío produce frases que nadie sabe de dónde salen."""
    out = render("Abrimos {next_opening}", {})
    assert out == "Abrimos {next_opening}"


def test_braces_that_are_not_placeholders_are_left_alone() -> None:
    # Sin motor de plantillas: nada de `{% if %}` ni llaves con mayúsculas o números.
    text = "Precio {PRECIO} y {1} y {  espacio }"
    assert render(text, {"branch_name": "x"}) == text


def test_finds_and_judges_placeholders() -> None:
    text = "{branch_name} {menu_link} {inventado}"
    assert find_placeholders(text) == {"branch_name", "menu_link", "inventado"}
    assert unknown_placeholders(text) == {"inventado"}


def test_an_order_placeholder_is_rejected_in_a_greeting() -> None:
    """No es un error de sintaxis: es un texto que saldría con un hueco al cliente."""
    bad = unknown_placeholders("Hola {order_total}", GREETING_PLACEHOLDERS)
    assert bad == {"order_total"}


def test_a_valid_greeting_has_nothing_unknown() -> None:
    text = "Hola, {branch_name}. Carta: {menu_link}. Abrimos {next_opening}"
    assert unknown_placeholders(text, GREETING_PLACEHOLDERS) == set()


# --- Próxima apertura, redactada como habla la gente -------------------------
def test_next_opening_uses_relative_days_when_it_can() -> None:
    # lunes = 0
    assert format_next_opening((0, 8 * 60), today_weekday=0) == "hoy a las 8:00"
    assert format_next_opening((1, 8 * 60), today_weekday=0) == "mañana a las 8:00"
    # Más lejos, el nombre del día: más útil que "en 4 días".
    assert format_next_opening((3, 10 * 60 + 30), today_weekday=0) == "el jueves a las 10:30"


def test_next_opening_wraps_around_the_week() -> None:
    # Domingo (6) mirando al lunes (0): es "mañana", no "hace seis días".
    assert format_next_opening((0, 9 * 60), today_weekday=6) == "mañana a las 9:00"


def test_no_hours_means_no_sentence() -> None:
    """Una sede sin horarios cargados no puede prometer una hora de apertura."""
    assert format_next_opening(None, today_weekday=2) is None


# --- La frase de horario -----------------------------------------------------
def test_hours_line_open_says_until_when() -> None:
    assert format_hours_line((22 * 60, True), None) == "hoy hasta las 22:00"


def test_hours_line_drops_today_when_the_close_is_tomorrow() -> None:
    """A las once de la noche, "hoy hasta las 2:00" es mentira con un reloj puesto."""
    assert format_hours_line((2 * 60, False), None) == "hasta las 2:00"


def test_hours_line_closed_says_when_it_opens() -> None:
    line = format_hours_line(None, "mañana a las 8:00")
    assert line == "cerrados; abrimos mañana a las 8:00"


def test_hours_line_without_hours_says_nothing() -> None:
    """Sin horarios cargados no hay frase — y el cliente NO ve el marcador crudo."""
    assert format_hours_line(None, None) is None


def test_hours_line_is_a_faq_placeholder_but_not_a_greeting_one() -> None:
    """El saludo ya resuelve lo mismo con sus dos variantes; la FAQ no tiene variantes."""
    assert unknown_placeholders("Horario: {hours_line}", FAQ_PLACEHOLDERS) == set()
    assert unknown_placeholders("Horario: {hours_line}", GREETING_PLACEHOLDERS) == {
        "hours_line"
    }


def test_faq_placeholders_exclude_order_data() -> None:
    """Una FAQ disparada por la palabra "horario" no tiene pedido del que hablar."""
    assert unknown_placeholders("Tu pedido {order_number}", FAQ_PLACEHOLDERS) == {
        "order_number"
    }
