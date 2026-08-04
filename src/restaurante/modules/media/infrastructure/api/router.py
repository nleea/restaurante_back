"""Media API: presigned R2 uploads for business images (admin, `menu.manage`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.media.service import presign_business_image
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.storage.deps import build_object_storage

router = APIRouter(prefix="/media", tags=["media"])

TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]
_MANAGE = Depends(require_permission("menu.manage"))


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class PresignRequest(_CamelModel):
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    content_type: Annotated[str, Field(min_length=1, max_length=100)]


class PresignResponse(_CamelModel):
    upload_url: str
    public_url: str


@router.post("/presign", response_model=PresignResponse, dependencies=[_MANAGE])
async def presign(payload: PresignRequest, tenant_id: TenantDep) -> PresignResponse:
    """A short-lived presigned PUT URL for a logo + the object's final public URL.

    The browser PUTs the file straight to R2 with the returned ``uploadUrl``; on success it
    uses ``publicUrl``. Returns a clear error when R2 is not configured.
    """
    upload_url, public_url = presign_business_image(
        tenant_id,
        payload.content_type,
        storage=build_object_storage(),
        now=datetime.now(UTC),
        object_id=uuid.uuid4(),
    )
    return PresignResponse(upload_url=upload_url, public_url=public_url)
