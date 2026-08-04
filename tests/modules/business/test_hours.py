"""Pure operating-hours logic: open-at + next-opening, incl. overnight and closed days."""

from __future__ import annotations

from restaurante.modules.business.domain.hours import (
    HoursWindow,
    closing_at,
    is_open_at,
    next_opening,
)

# Weekdays: 0=Mon … 6=Sun. Minutes from midnight.
MON, TUE, FRI, SAT, SUN = 0, 1, 4, 5, 6


def test_normal_window_open_and_closed() -> None:
    windows = [HoursWindow(MON, 8 * 60, 17 * 60)]  # Mon 08:00–17:00
    assert is_open_at(windows, MON, 10 * 60) is True
    assert is_open_at(windows, MON, 8 * 60) is True  # inclusive open
    assert is_open_at(windows, MON, 17 * 60) is False  # exclusive close
    assert is_open_at(windows, MON, 7 * 60) is False
    assert is_open_at(windows, TUE, 10 * 60) is False


def test_overnight_window_spans_next_day() -> None:
    windows = [HoursWindow(FRI, 20 * 60, 2 * 60)]  # Fri 20:00 → Sat 02:00
    assert is_open_at(windows, FRI, 23 * 60) is True
    assert is_open_at(windows, SAT, 1 * 60) is True  # bleeds into Saturday
    assert is_open_at(windows, SAT, 3 * 60) is False
    assert is_open_at(windows, FRI, 19 * 60) is False


def test_closed_day_has_no_window() -> None:
    windows = [HoursWindow(MON, 8 * 60, 12 * 60)]
    assert is_open_at(windows, SUN, 10 * 60) is False


def test_next_opening_later_today() -> None:
    windows = [HoursWindow(MON, 8 * 60, 12 * 60), HoursWindow(MON, 14 * 60, 20 * 60)]
    # Closed at 13:00 → next opening is the 14:00 window today.
    assert next_opening(windows, MON, 13 * 60) == (MON, 14 * 60)


def test_next_opening_wraps_to_a_later_day() -> None:
    windows = [HoursWindow(MON, 8 * 60, 12 * 60), HoursWindow(SAT, 9 * 60, 15 * 60)]
    # After Monday's window, the next opening is Saturday.
    assert next_opening(windows, MON, 13 * 60) == (SAT, 9 * 60)


def test_next_opening_wraps_around_the_week() -> None:
    windows = [HoursWindow(MON, 8 * 60, 12 * 60)]
    # Sunday afternoon → wrap to Monday.
    assert next_opening(windows, SUN, 18 * 60) == (MON, 8 * 60)


def test_next_opening_none_without_windows() -> None:
    assert next_opening([], MON, 0) is None


# --- closing_at: lo que hace correcta la frase de horario a cualquier hora ---
def test_closing_at_reports_todays_close() -> None:
    windows = [HoursWindow(MON, 8 * 60, 22 * 60)]
    assert closing_at(windows, MON, 14 * 60) == (22 * 60, True)


def test_closing_at_is_none_while_closed() -> None:
    windows = [HoursWindow(MON, 8 * 60, 22 * 60)]
    assert closing_at(windows, MON, 23 * 60) is None
    assert closing_at(windows, TUE, 14 * 60) is None
    assert closing_at([], MON, 14 * 60) is None


def test_closing_at_flags_an_overnight_close_as_not_today() -> None:
    """A las 23:00 de un viernes que cierra a las 2:00, "hoy hasta las 2:00" es mentira."""
    windows = [HoursWindow(FRI, 20 * 60, 2 * 60)]
    assert closing_at(windows, FRI, 23 * 60) == (2 * 60, False)
    # Ya pasada la medianoche, ese mismo cierre SÍ es de hoy.
    assert closing_at(windows, SAT, 1 * 60) == (2 * 60, True)


def test_closing_at_takes_the_latest_close() -> None:
    """"Abierto hasta X" es el cierre más tardío, no el primero que se encuentre."""
    windows = [HoursWindow(MON, 8 * 60, 12 * 60), HoursWindow(MON, 10 * 60, 20 * 60)]
    assert closing_at(windows, MON, 11 * 60) == (20 * 60, True)
    # Y una ventana que cruza la medianoche cierra después que una que acaba hoy.
    overlapping = [HoursWindow(MON, 8 * 60, 23 * 60), HoursWindow(MON, 20 * 60, 2 * 60)]
    assert closing_at(overlapping, MON, 21 * 60) == (2 * 60, False)
