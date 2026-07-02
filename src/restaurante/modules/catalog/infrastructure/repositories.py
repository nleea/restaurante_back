"""Persistence adapter for the Catalog module over SQLAlchemy async.

Catalog tables are global (no tenancy), so queries are not tenant-filtered. Each
write commits its own unit of work; the unique `iso_code` violation is translated
to ``ConflictError``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.catalog.domain.entities import City, Country, UnitOfMeasure
from restaurante.modules.catalog.infrastructure.models import (
    CityModel,
    CountryModel,
    UnitOfMeasureModel,
)
from restaurante.shared.domain.errors import ConflictError


def _country(m: CountryModel) -> Country:
    return Country(id=m.id, name=m.name, iso_code=m.iso_code)


def _city(m: CityModel) -> City:
    return City(
        id=m.id,
        country_id=m.country_id,
        name=m.name,
        state_province=m.state_province,
    )


def _unit(m: UnitOfMeasureModel) -> UnitOfMeasure:
    return UnitOfMeasure(
        id=m.id,
        name=m.name,
        abbreviation=m.abbreviation,
        base_unit_id=m.base_unit_id,
        conversion_factor=m.conversion_factor,
    )


class SqlAlchemyCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Countries ---------------------------------------------------------
    async def create_country(self, country: Country) -> Country:
        model = CountryModel(name=country.name, iso_code=country.iso_code)
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un país con ese código ISO.") from exc
        await self._session.refresh(model)
        return _country(model)

    async def _get_country_model(self, country_id: uuid.UUID) -> CountryModel | None:
        stmt = select(CountryModel).where(CountryModel.id == country_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_country(self, country_id: uuid.UUID) -> Country | None:
        model = await self._get_country_model(country_id)
        return _country(model) if model else None

    async def iso_code_exists(self, iso_code: str) -> bool:
        stmt = select(CountryModel.id).where(CountryModel.iso_code == iso_code)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_countries(self) -> list[Country]:
        stmt = select(CountryModel).order_by(CountryModel.name)
        return [_country(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_country(
        self, country_id: uuid.UUID, fields: dict[str, Any]
    ) -> Country | None:
        model = await self._get_country_model(country_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _country(model)

    # --- Cities ------------------------------------------------------------
    async def country_exists(self, country_id: uuid.UUID) -> bool:
        stmt = select(CountryModel.id).where(CountryModel.id == country_id)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def create_city(self, city: City) -> City:
        model = CityModel(
            country_id=city.country_id,
            name=city.name,
            state_province=city.state_province,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _city(model)

    async def _get_city_model(self, city_id: uuid.UUID) -> CityModel | None:
        stmt = select(CityModel).where(CityModel.id == city_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_city(self, city_id: uuid.UUID) -> City | None:
        model = await self._get_city_model(city_id)
        return _city(model) if model else None

    async def list_cities(
        self, *, country_id: uuid.UUID | None = None
    ) -> list[City]:
        stmt = select(CityModel)
        if country_id is not None:
            stmt = stmt.where(CityModel.country_id == country_id)
        stmt = stmt.order_by(CityModel.name)
        return [_city(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_city(
        self, city_id: uuid.UUID, fields: dict[str, Any]
    ) -> City | None:
        model = await self._get_city_model(city_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _city(model)

    # --- Units of measure --------------------------------------------------
    async def unit_exists(self, unit_id: uuid.UUID) -> bool:
        stmt = select(UnitOfMeasureModel.id).where(UnitOfMeasureModel.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def create_unit(self, unit: UnitOfMeasure) -> UnitOfMeasure:
        model = UnitOfMeasureModel(
            name=unit.name,
            abbreviation=unit.abbreviation,
            base_unit_id=unit.base_unit_id,
            conversion_factor=unit.conversion_factor,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _unit(model)

    async def _get_unit_model(self, unit_id: uuid.UUID) -> UnitOfMeasureModel | None:
        stmt = select(UnitOfMeasureModel).where(UnitOfMeasureModel.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_unit(self, unit_id: uuid.UUID) -> UnitOfMeasure | None:
        model = await self._get_unit_model(unit_id)
        return _unit(model) if model else None

    async def list_units(self) -> list[UnitOfMeasure]:
        stmt = select(UnitOfMeasureModel).order_by(UnitOfMeasureModel.name)
        return [_unit(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_unit(
        self, unit_id: uuid.UUID, fields: dict[str, Any]
    ) -> UnitOfMeasure | None:
        model = await self._get_unit_model(unit_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _unit(model)
