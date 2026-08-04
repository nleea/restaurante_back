"""SigV4 presigned-PUT signing for R2 (structure, determinism, sensitivity)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from restaurante.shared.storage.r2 import R2Storage

_NOW = datetime(2026, 7, 21, 15, 30, 0, tzinfo=UTC)


def _storage(secret: str = "secretkey", access: str = "accesskey") -> R2Storage:
    return R2Storage(
        account_id="acct123",
        access_key_id=access,
        secret_access_key=secret,
        bucket="media",
        public_base_url="https://cdn.example.com",
    )


def test_is_configured() -> None:
    assert _storage().is_configured is True
    empty = R2Storage(
        account_id="", access_key_id="", secret_access_key="", bucket="", public_base_url=""
    )
    assert empty.is_configured is False


def test_public_url_joins_base_and_key() -> None:
    assert _storage().public_url("logos/t/x.png") == "https://cdn.example.com/logos/t/x.png"


def test_presigned_url_structure() -> None:
    url = _storage().presign_put("logos/t/x.png", now=_NOW, expires_seconds=300)
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "acct123.r2.cloudflarestorage.com"
    assert parsed.path == "/media/logos/t/x.png"
    q = parse_qs(parsed.query)
    assert q["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert q["X-Amz-Expires"] == ["300"]
    assert q["X-Amz-SignedHeaders"] == ["host"]
    assert q["X-Amz-Date"] == ["20260721T153000Z"]
    assert q["X-Amz-Credential"] == ["accesskey/20260721/auto/s3/aws4_request"]
    assert len(q["X-Amz-Signature"][0]) == 64  # hex sha256


def test_signature_is_deterministic() -> None:
    a = _storage().presign_put("logos/t/x.png", now=_NOW)
    b = _storage().presign_put("logos/t/x.png", now=_NOW)
    assert a == b


def test_explicit_endpoint_url_is_used_and_signed() -> None:
    storage = R2Storage(
        account_id="acct123",
        access_key_id="ak",
        secret_access_key="sk",
        bucket="media",
        public_base_url="https://cdn.example.com",
        endpoint_url="https://acct123.eu.r2.cloudflarestorage.com",
    )
    url = storage.presign_put("logos/t/x.png", now=_NOW)
    parsed = urlparse(url)
    assert parsed.netloc == "acct123.eu.r2.cloudflarestorage.com"  # jurisdiction host
    assert parsed.path == "/media/logos/t/x.png"
    # Signed against that host → different signature than the default endpoint.
    assert url != _storage().presign_put("logos/t/x.png", now=_NOW)


def test_signature_changes_with_secret_and_key() -> None:
    base = _storage().presign_put("logos/t/x.png", now=_NOW)
    other_secret = _storage(secret="different").presign_put("logos/t/x.png", now=_NOW)
    other_object = _storage().presign_put("logos/t/y.png", now=_NOW)
    assert base != other_secret
    assert base != other_object
