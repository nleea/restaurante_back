"""Media presign: logic (configured/unconfigured/bad type) + endpoint auth gate."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from restaurante.modules.media.service import presign_business_image
from restaurante.shared.domain.errors import ValidationError
from restaurante.shared.storage.r2 import R2Storage

_NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def _configured() -> R2Storage:
    return R2Storage(
        account_id="acct",
        access_key_id="ak",
        secret_access_key="sk",
        bucket="media",
        public_base_url="https://cdn.example.com",
    )


def _unconfigured() -> R2Storage:
    return R2Storage(
        account_id="", access_key_id="", secret_access_key="", bucket="", public_base_url=""
    )


def test_presign_returns_upload_and_public_urls() -> None:
    tenant = uuid.uuid4()
    oid = uuid.uuid4()
    upload_url, public_url = presign_business_image(
        tenant, "image/png", storage=_configured(), now=_NOW, object_id=oid
    )
    key = f"logos/{tenant}/{oid.hex}.png"
    assert public_url == f"https://cdn.example.com/{key}"
    assert upload_url.startswith("https://acct.r2.cloudflarestorage.com/media/" + key)
    assert "X-Amz-Signature=" in upload_url


def test_presign_unsupported_content_type() -> None:
    with pytest.raises(ValidationError):
        presign_business_image(
            uuid.uuid4(), "application/pdf", storage=_configured(), now=_NOW,
            object_id=uuid.uuid4(),
        )


def test_presign_unconfigured_storage() -> None:
    with pytest.raises(ValidationError):
        presign_business_image(
            uuid.uuid4(), "image/png", storage=_unconfigured(), now=_NOW,
            object_id=uuid.uuid4(),
        )


async def test_presign_endpoint_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/media/presign", json={"filename": "logo.png", "contentType": "image/png"}
    )
    assert resp.status_code == 401, resp.text  # menu.manage gate, no token
