"""El comprobante se valida ANTES de escribir. Es la razón de que los bytes pasen por la API.

Sin base de datos y sin red: el almacenamiento y el cliente HTTP van como dobles, porque lo que
se prueba es la puerta, no R2.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from restaurante.modules.orders.infrastructure.payment_proof import (
    MAX_PROOF_BYTES,
    store_payment_proof,
)
from restaurante.shared.domain.errors import ValidationError

TENANT = uuid.uuid4()
ORDER = uuid.uuid4()


class FakeStorage:
    def __init__(self, configured: bool = True) -> None:
        self.is_configured = configured
        self.keys: list[str] = []

    def presign_put(self, key: str, *, now: Any, expires_seconds: int = 300) -> str:
        self.keys.append(key)
        return f"https://r2.test/{key}?signed"

    def public_url(self, key: str) -> str:
        return f"https://cdn.test/{key}"


class FakeHttp:
    """Cuenta los PUT. Si alguno ocurre en un caso inválido, la prueba lo caza."""

    def __init__(self) -> None:
        self.puts: list[tuple[str, int]] = []

    async def put(self, url: str, *, content: bytes, headers: dict[str, str]) -> Any:
        self.puts.append((url, len(content)))
        return type("Resp", (), {"raise_for_status": lambda self: None})()

    async def aclose(self) -> None:  # pragma: no cover - nunca se cierra el doble
        pass


async def _store(content_type: str, data: bytes, storage: FakeStorage, http: FakeHttp) -> str:
    return await store_payment_proof(
        TENANT, ORDER, content_type, data, storage=storage, client=http  # type: ignore[arg-type]
    )


async def test_a_receipt_is_stored_under_its_tenant_and_order() -> None:
    storage, http = FakeStorage(), FakeHttp()
    url = await _store("image/jpeg", b"unos bytes", storage, http)

    assert storage.keys[0].startswith(f"payment-proofs/{TENANT}/{ORDER}/")
    assert storage.keys[0].endswith(".jpg")
    assert url.startswith("https://cdn.test/payment-proofs/")
    assert len(http.puts) == 1


@pytest.mark.parametrize(
    ("content_type", "data"),
    [
        ("text/html", b"<script>"),
        ("application/zip", b"PK"),
        ("image/jpeg", b""),
        ("image/jpeg", b"x" * (MAX_PROOF_BYTES + 1)),
    ],
)
async def test_what_is_not_a_receipt_never_reaches_the_bucket(
    content_type: str, data: bytes
) -> None:
    storage, http = FakeStorage(), FakeHttp()
    with pytest.raises(ValidationError):
        await _store(content_type, data, storage, http)
    assert http.puts == [], "se rechazó, pero escribió igual"
    assert storage.keys == []


async def test_without_storage_configured_nothing_is_attempted() -> None:
    storage, http = FakeStorage(configured=False), FakeHttp()
    with pytest.raises(ValidationError):
        await _store("image/png", b"bytes", storage, http)
    assert http.puts == []


async def test_a_pdf_is_a_valid_receipt() -> None:
    """Los bancos mandan PDF; rechazarlo obligaría al cliente a hacerle una foto a la pantalla."""
    storage, http = FakeStorage(), FakeHttp()
    await _store("application/pdf", b"%PDF-1.4", storage, http)
    assert storage.keys[0].endswith(".pdf")
