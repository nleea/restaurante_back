"""Pure helpers over structured operating hours (framework-free, fully unit-tested).

A week is a set of open WINDOWS. Each window is a weekday + an open/close time expressed
as minutes-from-midnight. A window whose ``close_minute <= open_minute`` crosses midnight
into the next day. A weekday with no window is closed. Times are naive local (the branch's
local time); timezone handling is out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass

MINUTES_PER_DAY = 24 * 60
DAYS = 7


@dataclass(frozen=True)
class HoursWindow:
    """One open interval. ``weekday`` 0=Monday … 6=Sunday; minutes in [0, 1440]."""

    weekday: int
    open_minute: int
    close_minute: int

    @property
    def crosses_midnight(self) -> bool:
        return self.close_minute <= self.open_minute


def _covers(window: HoursWindow, weekday: int, minute: int) -> bool:
    """Does ``window`` cover (weekday, minute), accounting for midnight crossing?"""
    if not window.crosses_midnight:
        return window.weekday == weekday and window.open_minute <= minute < window.close_minute
    # Overnight: [open, 1440) on its own weekday, and [0, close) on the next weekday.
    if window.weekday == weekday and minute >= window.open_minute:
        return True
    prev_day = (weekday - 1) % DAYS
    return window.weekday == prev_day and minute < window.close_minute


def is_open_at(windows: list[HoursWindow], weekday: int, minute: int) -> bool:
    """Whether any window is open at the given weekday/minute."""
    return any(_covers(w, weekday, minute) for w in windows)


def _closing_of(
    window: HoursWindow, weekday: int, minute: int
) -> tuple[int, bool] | None:
    """``(close_minute, closes_on_this_weekday)`` if this window covers the moment."""
    if not _covers(window, weekday, minute):
        return None
    if not window.crosses_midnight:
        return window.close_minute, True
    # Overnight: on its own weekday it closes tomorrow; on the following day, today.
    if window.weekday == weekday and minute >= window.open_minute:
        return window.close_minute, False
    return window.close_minute, True


def closing_at(
    windows: list[HoursWindow], weekday: int, minute: int
) -> tuple[int, bool] | None:
    """When the currently open window closes, or ``None`` when closed.

    Returns ``(close_minute, closes_on_this_weekday)``. The flag matters for prose: a window
    running 20:00→02:00 does not close "today" when it is 23:00, and saying so would be a lie
    with a clock on it.

    With overlapping windows the LATEST close wins — that is what "open until X" means.
    """
    candidates = [
        closing
        for closing in (_closing_of(w, weekday, minute) for w in windows)
        if closing is not None
    ]
    if not candidates:
        return None
    # `not same_day` sorts a next-day close after a same-day one; then the later clock time.
    return max(candidates, key=lambda closing: (not closing[1], closing[0]))


def next_opening(
    windows: list[HoursWindow], weekday: int, minute: int
) -> tuple[int, int] | None:
    """The next (weekday, minute) at which the business opens, searching up to 7 days.

    Returns ``None`` when there are no windows at all. If currently open, returns the
    current window's open time is NOT what we want — callers use this only when closed,
    so we return the earliest opening strictly reachable from now (today later, then the
    following days). Today's already-passed openings are skipped.
    """
    if not windows:
        return None
    # today (only openings at/after `minute`), then each subsequent day from its start.
    for offset in range(DAYS + 1):
        day = (weekday + offset) % DAYS
        floor = minute if offset == 0 else 0
        candidates = sorted(
            w.open_minute for w in windows if w.weekday == day and w.open_minute >= floor
        )
        if candidates:
            return day, candidates[0]
    return None
