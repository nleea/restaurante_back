"""Application service for the Catalog module (global reference data).

Owns countries, cities and units of measure. Data is global (no tenancy);
RBAC is enforced at the API layer. Validates ISO-code uniqueness, city→country
references, and the unit base/conversion-factor integrity rules.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from restaurante.modules.catalog.domain.entities import City, Country, UnitOfMeasure
from restaurante.modules.catalog.domain.ports import CatalogRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


class CatalogService:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    # --- guards ------------------------------------------------------------
    async def _require_country(self, country_id: uuid.UUID) -> None:
        if not await self._repo.country_exists(country_id):
            raise NotFoundError(f"País no encontrado: {country_id}")

    async def _require_unit(self, unit_id: uuid.UUID) -> None:
        if not await self._repo.unit_exists(unit_id):
            raise NotFoundError(f"Unidad de medida no encontrada: {unit_id}")

    def _validate_base_factor(
        self, base_unit_id: uuid.UUID | None, conversion_factor: Decimal | None
    ) -> None:
        if (base_unit_id is None) != (conversion_factor is None):
            raise ValidationError(
                "base_unit_id y conversion_factor deben definirse juntos o ninguno."
            )
        if conversion_factor is not None and conversion_factor <= 0:
            raise ValidationError("El factor de conversión debe ser positivo.")

    # --- Countries ---------------------------------------------------------
    async def create_country(self, name: str, iso_code: str) -> Country:
        if await self._repo.iso_code_exists(iso_code):
            raise ConflictError("Ya existe un país con ese código ISO.")
        return await self._repo.create_country(Country(name=name, iso_code=iso_code))

    async def list_countries(self) -> list[Country]:
        return await self._repo.list_countries()

    async def get_country(self, country_id: uuid.UUID) -> Country:
        country = await self._repo.get_country(country_id)
        if country is None:
            raise NotFoundError(f"País no encontrado: {country_id}")
        return country

    async def update_country(
        self, country_id: uuid.UUID, fields: dict[str, Any]
    ) -> Country:
        updated = await self._repo.update_country(country_id, fields)
        if updated is None:
            raise NotFoundError(f"País no encontrado: {country_id}")
        return updated

    # --- Cities ------------------------------------------------------------
    async def create_city(
        self, country_id: uuid.UUID, name: str, state_province: str | None = None
    ) -> City:
        await self._require_country(country_id)
        return await self._repo.create_city(
            City(country_id=country_id, name=name, state_province=state_province)
        )

    async def list_cities(self, *, country_id: uuid.UUID | None = None) -> list[City]:
        return await self._repo.list_cities(country_id=country_id)

    async def get_city(self, city_id: uuid.UUID) -> City:
        city = await self._repo.get_city(city_id)
        if city is None:
            raise NotFoundError(f"Ciudad no encontrada: {city_id}")
        return city

    async def update_city(
        self, city_id: uuid.UUID, fields: dict[str, Any]
    ) -> City:
        if fields.get("country_id") is not None:
            await self._require_country(fields["country_id"])
        updated = await self._repo.update_city(city_id, fields)
        if updated is None:
            raise NotFoundError(f"Ciudad no encontrada: {city_id}")
        return updated

    # --- Units of measure --------------------------------------------------
    async def create_unit(
        self,
        name: str,
        abbreviation: str,
        base_unit_id: uuid.UUID | None = None,
        conversion_factor: Decimal | None = None,
    ) -> UnitOfMeasure:
        self._validate_base_factor(base_unit_id, conversion_factor)
        if base_unit_id is not None:
            await self._require_unit(base_unit_id)
        return await self._repo.create_unit(
            UnitOfMeasure(
                name=name,
                abbreviation=abbreviation,
                base_unit_id=base_unit_id,
                conversion_factor=conversion_factor,
            )
        )

    async def list_units(self) -> list[UnitOfMeasure]:
        return await self._repo.list_units()

    async def get_unit(self, unit_id: uuid.UUID) -> UnitOfMeasure:
        unit = await self._repo.get_unit(unit_id)
        if unit is None:
            raise NotFoundError(f"Unidad de medida no encontrada: {unit_id}")
        return unit

    async def update_unit(
        self, unit_id: uuid.UUID, fields: dict[str, Any]
    ) -> UnitOfMeasure:
        current = await self.get_unit(unit_id)
        base_unit_id = (
            fields["base_unit_id"]
            if "base_unit_id" in fields
            else current.base_unit_id
        )
        conversion_factor = (
            fields["conversion_factor"]
            if "conversion_factor" in fields
            else current.conversion_factor
        )
        self._validate_base_factor(base_unit_id, conversion_factor)
        if base_unit_id is not None:
            if base_unit_id == unit_id:
                raise ValidationError("Una unidad no puede ser su propia base.")
            await self._require_unit(base_unit_id)
        updated = await self._repo.update_unit(unit_id, fields)
        if updated is None:
            raise NotFoundError(f"Unidad de medida no encontrada: {unit_id}")
        return updated
