"""Pydantic schemas for the Guest Profile API.

Wire contract is camelCase via the shared ``to_camel`` alias generator. The read
model deliberately omits the token: it lives only in the httponly ``guest_token``
cookie and must never be exposed to client JavaScript.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from restaurante.modules.guest_profile.domain.entities import GuestProfile


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class GuestProfileWrite(_CamelModel):
    """Contact fields a guest may create/update. All optional (progressive fill)."""

    name: Annotated[str | None, Field(max_length=120)] = None
    address: Annotated[str | None, Field(max_length=255)] = None
    phone: Annotated[str | None, Field(max_length=30)] = None


class GuestProfileRead(_CamelModel):
    """Null-friendly read: empty when there is no cookie or no matching row."""

    name: str | None = None
    address: str | None = None
    phone: str | None = None

    @classmethod
    def from_entity(cls, profile: GuestProfile | None) -> GuestProfileRead:
        if profile is None:
            return cls()
        return cls(name=profile.name, address=profile.address, phone=profile.phone)
