"""ORM models of the Catalog module.

Global catalogs shared across tenants, so they use plain `Base` (no tenancy
mixin, no automatic tenant filter).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base


class CountryModel(Base):
    __tablename__ = "countries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    iso_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)


class CityModel(Base):
    __tablename__ = "cities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    country_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)


class UnitOfMeasureModel(Base):
    """Unit of measure with optional self-reference to its family base unit."""

    __tablename__ = "units_of_measure"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False)
    base_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True
    )
    conversion_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
