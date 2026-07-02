"""Ports (interfaces) of the Catalog module.

Catalog data is global (no tenancy), so methods take no `tenant_id`.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.catalog.domain.entities import City, Country, UnitOfMeasure


class CatalogRepository(Protocol):
    # --- Countries ---------------------------------------------------------
    async def create_country(self, country: Country) -> Country: ...

    async def get_country(self, country_id: uuid.UUID) -> Country | None: ...

    async def iso_code_exists(self, iso_code: str) -> bool: ...

    async def list_countries(self) -> list[Country]: ...

    async def update_country(
        self, country_id: uuid.UUID, fields: dict[str, Any]
    ) -> Country | None: ...

    # --- Cities ------------------------------------------------------------
    async def country_exists(self, country_id: uuid.UUID) -> bool: ...

    async def create_city(self, city: City) -> City: ...

    async def get_city(self, city_id: uuid.UUID) -> City | None: ...

    async def list_cities(
        self, *, country_id: uuid.UUID | None = None
    ) -> list[City]: ...

    async def update_city(
        self, city_id: uuid.UUID, fields: dict[str, Any]
    ) -> City | None: ...

    # --- Units of measure --------------------------------------------------
    async def unit_exists(self, unit_id: uuid.UUID) -> bool: ...

    async def create_unit(self, unit: UnitOfMeasure) -> UnitOfMeasure: ...

    async def get_unit(self, unit_id: uuid.UUID) -> UnitOfMeasure | None: ...

    async def list_units(self) -> list[UnitOfMeasure]: ...

    async def update_unit(
        self, unit_id: uuid.UUID, fields: dict[str, Any]
    ) -> UnitOfMeasure | None: ...
