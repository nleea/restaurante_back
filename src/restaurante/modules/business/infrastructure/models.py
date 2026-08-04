"""ORM model of the Business module: structured per-branch operating hours."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, BranchScopedMixin, TimestampMixin


class OperatingHoursModel(Base, BranchScopedMixin, TimestampMixin):
    """One open window per row (branch, weekday, open/close minutes).

    Multiple rows per (branch, weekday) express split windows (e.g. lunch + dinner).
    A weekday with no row is closed. Times are minutes-from-midnight in [0, 1440];
    ``close_minute <= open_minute`` crosses midnight.
    """

    __tablename__ = "operating_hours"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    open_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    close_minute: Mapped[int] = mapped_column(Integer, nullable=False)
