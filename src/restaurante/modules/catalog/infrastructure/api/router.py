"""Catalog API: global reference data (countries, cities, units of measure).

RBAC: reads `catalog.read`; writes `catalog.manage`. Data is global (no tenancy).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.catalog.infrastructure.api.deps import (
    CatalogServiceDep,
    TenantDep,
)
from restaurante.modules.catalog.infrastructure.api.schemas import (
    CityResponse,
    CountryResponse,
    CreateCityRequest,
    CreateCountryRequest,
    CreateUnitRequest,
    UnitOfMeasureResponse,
    UpdateCityRequest,
    UpdateCountryRequest,
    UpdateUnitRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/catalog", tags=["catalog"])

_READ = Depends(require_permission("catalog.read"))
_MANAGE = Depends(require_permission("catalog.manage"))


# --- Countries --------------------------------------------------------------
@router.post(
    "/countries", response_model=CountryResponse, status_code=201, dependencies=[_MANAGE]
)
async def create_country(
    payload: CreateCountryRequest, service: CatalogServiceDep, tenant_id: TenantDep
) -> CountryResponse:
    country = await service.create_country(payload.name, payload.iso_code)
    return CountryResponse.model_validate(country, from_attributes=True)


@router.get("/countries", response_model=list[CountryResponse], dependencies=[_READ])
async def list_countries(
    service: CatalogServiceDep, tenant_id: TenantDep
) -> list[CountryResponse]:
    countries = await service.list_countries()
    return [CountryResponse.model_validate(c, from_attributes=True) for c in countries]


@router.patch(
    "/countries/{country_id}", response_model=CountryResponse, dependencies=[_MANAGE]
)
async def update_country(
    country_id: uuid.UUID,
    payload: UpdateCountryRequest,
    service: CatalogServiceDep,
    tenant_id: TenantDep,
) -> CountryResponse:
    country = await service.update_country(
        country_id, payload.model_dump(exclude_unset=True)
    )
    return CountryResponse.model_validate(country, from_attributes=True)


# --- Cities -----------------------------------------------------------------
@router.post("/cities", response_model=CityResponse, status_code=201, dependencies=[_MANAGE])
async def create_city(
    payload: CreateCityRequest, service: CatalogServiceDep, tenant_id: TenantDep
) -> CityResponse:
    city = await service.create_city(
        payload.country_id, payload.name, payload.state_province
    )
    return CityResponse.model_validate(city, from_attributes=True)


@router.get("/cities", response_model=list[CityResponse], dependencies=[_READ])
async def list_cities(
    service: CatalogServiceDep,
    tenant_id: TenantDep,
    country_id: uuid.UUID | None = None,
) -> list[CityResponse]:
    cities = await service.list_cities(country_id=country_id)
    return [CityResponse.model_validate(c, from_attributes=True) for c in cities]


@router.patch("/cities/{city_id}", response_model=CityResponse, dependencies=[_MANAGE])
async def update_city(
    city_id: uuid.UUID,
    payload: UpdateCityRequest,
    service: CatalogServiceDep,
    tenant_id: TenantDep,
) -> CityResponse:
    city = await service.update_city(city_id, payload.model_dump(exclude_unset=True))
    return CityResponse.model_validate(city, from_attributes=True)


# --- Units of measure -------------------------------------------------------
@router.post(
    "/units", response_model=UnitOfMeasureResponse, status_code=201, dependencies=[_MANAGE]
)
async def create_unit(
    payload: CreateUnitRequest, service: CatalogServiceDep, tenant_id: TenantDep
) -> UnitOfMeasureResponse:
    unit = await service.create_unit(
        payload.name,
        payload.abbreviation,
        payload.base_unit_id,
        payload.conversion_factor,
    )
    return UnitOfMeasureResponse.model_validate(unit, from_attributes=True)


@router.get("/units", response_model=list[UnitOfMeasureResponse], dependencies=[_READ])
async def list_units(
    service: CatalogServiceDep, tenant_id: TenantDep
) -> list[UnitOfMeasureResponse]:
    units = await service.list_units()
    return [UnitOfMeasureResponse.model_validate(u, from_attributes=True) for u in units]


@router.patch(
    "/units/{unit_id}", response_model=UnitOfMeasureResponse, dependencies=[_MANAGE]
)
async def update_unit(
    unit_id: uuid.UUID,
    payload: UpdateUnitRequest,
    service: CatalogServiceDep,
    tenant_id: TenantDep,
) -> UnitOfMeasureResponse:
    unit = await service.update_unit(unit_id, payload.model_dump(exclude_unset=True))
    return UnitOfMeasureResponse.model_validate(unit, from_attributes=True)
