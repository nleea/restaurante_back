"""Presign logic for business image uploads (pure, storage injected — fully testable)."""

from __future__ import annotations

import uuid
from datetime import datetime

from restaurante.shared.domain.errors import ValidationError
from restaurante.shared.storage.ports import StorageGateway

# Accepted image content types → object extension.
_IMAGE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def presign_business_image(
    tenant_id: uuid.UUID,
    content_type: str,
    *,
    storage: StorageGateway,
    now: datetime,
    object_id: uuid.UUID,
) -> tuple[str, str]:
    """(uploadUrl, publicUrl) for a tenant-scoped logo object, or raise on bad input/config."""
    if content_type not in _IMAGE_EXT:
        raise ValidationError(f"Tipo de imagen no soportado: {content_type}")
    if not storage.is_configured:
        raise ValidationError(
            "El almacenamiento de imágenes (R2) no está configurado."
        )
    key = f"logos/{tenant_id}/{object_id.hex}{_IMAGE_EXT[content_type]}"
    return storage.presign_put(key, now=now), storage.public_url(key)
