"""Domain entities of the Catalog module (framework-free dataclasses).

Global reference data (no tenancy). Required business fields come first; `id` and
optional fields come last with defaults.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Country:
    """A country. Reusable global catalog (maps from `pais`)."""

    name: str
    iso_code: str
    id: uuid.UUID | None = None


@dataclass
class City:
    """A city tied to a country (maps from `ciudad`)."""

    country_id: uuid.UUID
    name: str
    state_province: str | None = None
    id: uuid.UUID | None = None


@dataclass
class UnitOfMeasure:
    """A unit of measure (maps from `unidad_medida`).

    Each measurement family (weight, volume, count) has a base unit. For
    non-base units, `base_unit_id` points to the family base and
    `conversion_factor` converts towards it (e.g. kg -> g factor = 1000).
    """

    name: str
    abbreviation: str
    base_unit_id: uuid.UUID | None = None
    conversion_factor: Decimal | None = None
    id: uuid.UUID | None = None
