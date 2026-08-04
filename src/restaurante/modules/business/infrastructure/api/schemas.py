"""Pydantic schemas for the Business API (camelCase wire contract)."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from restaurante.modules.business.domain.entities import (
    BranchProfile,
    BusinessProfile,
    OperatingHours,
)


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class HoursWindowInput(_CamelModel):
    weekday: Annotated[int, Field(ge=0, le=6)]
    open_minute: Annotated[int, Field(ge=0, le=1439)]
    close_minute: Annotated[int, Field(ge=1, le=1440)]


class SetHoursRequest(_CamelModel):
    windows: list[HoursWindowInput]


class BranchDetailsInput(_CamelModel):
    id: uuid.UUID
    address: Annotated[str | None, Field(max_length=512)] = None
    phone: Annotated[str | None, Field(max_length=30)] = None
    # Omitido = déjalo como estaba. Es lo que el cliente ve en el saludo y en la carta.
    name: Annotated[str | None, Field(min_length=1, max_length=255)] = None


class UpdateProfileRequest(_CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    tax_id: Annotated[str | None, Field(max_length=50)] = None
    email: Annotated[str | None, Field(max_length=150)] = None
    phone: Annotated[str | None, Field(max_length=30)] = None
    # Business photo (the shared brand logo URL). None leaves the current photo unchanged.
    photo_url: Annotated[str | None, Field(max_length=1000)] = None
    #: QR de pago del negocio. `None` = no se toca; "" lo borra.
    payment_qr_url: Annotated[str | None, Field(max_length=1000)] = None
    branches: list[BranchDetailsInput] = Field(default_factory=list)


class OperatingHoursResponse(_CamelModel):
    id: uuid.UUID | None
    weekday: int
    open_minute: int
    close_minute: int

    @classmethod
    def of(cls, h: OperatingHours) -> OperatingHoursResponse:
        return cls(
            id=h.id,
            weekday=h.weekday,
            open_minute=h.open_minute,
            close_minute=h.close_minute,
        )


class BranchProfileResponse(_CamelModel):
    id: uuid.UUID
    name: str
    address: str | None = None
    phone: str | None = None
    is_primary: bool
    hours: list[OperatingHoursResponse]

    @classmethod
    def of(cls, b: BranchProfile) -> BranchProfileResponse:
        return cls(
            id=b.id,
            name=b.name,
            address=b.address,
            phone=b.phone,
            is_primary=b.is_primary,
            hours=[OperatingHoursResponse.of(h) for h in b.hours],
        )


class BusinessProfileResponse(_CamelModel):
    tenant_id: uuid.UUID
    name: str
    tax_id: str | None = None
    email: str | None = None
    phone: str | None = None
    photo_url: str | None = None
    payment_qr_url: str | None = None
    banner_url: str | None = None
    staff_count: int
    branches: list[BranchProfileResponse]

    @classmethod
    def of(cls, p: BusinessProfile) -> BusinessProfileResponse:
        return cls(
            tenant_id=p.tenant_id,
            name=p.name,
            tax_id=p.tax_id,
            email=p.email,
            phone=p.phone,
            photo_url=p.photo_url,
            payment_qr_url=p.payment_qr_url,
            banner_url=p.banner_url,
            staff_count=p.staff_count,
            branches=[BranchProfileResponse.of(b) for b in p.branches],
        )
