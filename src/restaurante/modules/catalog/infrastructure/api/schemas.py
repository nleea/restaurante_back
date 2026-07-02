"""Pydantic schemas for the Catalog API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class CountryResponse(BaseModel):
    id: uuid.UUID
    name: str
    iso_code: str


class CityResponse(BaseModel):
    id: uuid.UUID
    country_id: uuid.UUID
    name: str
    state_province: str | None = None


class UnitOfMeasureResponse(BaseModel):
    id: uuid.UUID
    name: str
    abbreviation: str
    base_unit_id: uuid.UUID | None = None
    conversion_factor: Decimal | None = None


# --- Requests ---------------------------------------------------------------


class CreateCountryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    iso_code: str = Field(min_length=2, max_length=3)


class UpdateCountryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    iso_code: str | None = Field(default=None, min_length=2, max_length=3)


class CreateCityRequest(BaseModel):
    country_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    state_province: str | None = Field(default=None, max_length=100)


class UpdateCityRequest(BaseModel):
    country_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    state_province: str | None = Field(default=None, max_length=100)


class CreateUnitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    abbreviation: str = Field(min_length=1, max_length=10)
    base_unit_id: uuid.UUID | None = None
    conversion_factor: Decimal | None = Field(default=None, gt=0)


class UpdateUnitRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    abbreviation: str | None = Field(default=None, min_length=1, max_length=10)
    base_unit_id: uuid.UUID | None = None
    conversion_factor: Decimal | None = Field(default=None, gt=0)
