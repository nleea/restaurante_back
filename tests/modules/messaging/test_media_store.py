"""Guardar el archivo de un mensaje entrante. Sin base y sin red: dobles.

La afirmación que se repite en varias pruebas es la misma: **nunca levanta**. Quien llama acaba de
guardar el mensaje del cliente, y lo único que está en juego aquí es el archivo — una excepción
costaría el mensaje.
"""

from __future__ import annotations

import uuid
from typing import Any

from restaurante.modules.messaging.domain.media import MAX_MEDIA_BYTES
from restaurante.modules.messaging.infrastructure.media_store import store_conversation_media

TENANT = uuid.uuid4()
CONVERSATION = uuid.uuid4()


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
    """Cuenta los PUT. Si alguno ocurre en un caso que debía rechazarse, la prueba lo caza."""

    def __init__(self, fail: bool = False) -> None:
        self.puts: list[tuple[str, int]] = []
        self._fail = fail

    async def put(self, url: str, *, content: bytes, headers: dict[str, str]) -> Any:
        self.puts.append((url, len(content)))
        if self._fail:
            raise RuntimeError("R2 caído")
        return type("Resp", (), {"raise_for_status": lambda self: None})()

    async def aclose(self) -> None:  # pragma: no cover - el doble no se cierra
        pass


async def _store(
    mime: str, data: bytes, storage: FakeStorage, http: FakeHttp
) -> str | None:
    return await store_conversation_media(
        TENANT, CONVERSATION, mime, data, storage=storage, client=http  # type: ignore[arg-type]
    )


async def test_the_key_carries_tenant_and_conversation() -> None:
    """Un objeto suelto en el bucket tiene que poder atribuirse sin consultar la base."""
    storage, http = FakeStorage(), FakeHttp()
    url = await _store("image/jpeg", b"unos bytes", storage, http)

    assert storage.keys[0].startswith(f"whatsapp-media/{TENANT}/{CONVERSATION}/")
    assert storage.keys[0].endswith(".jpg")
    assert url == f"https://cdn.test/{storage.keys[0]}"
    assert len(http.puts) == 1


async def test_a_pdf_keeps_its_extension() -> None:
    storage, http = FakeStorage(), FakeHttp()
    await _store("application/pdf", b"%PDF-1.4", storage, http)
    assert storage.keys[0].endswith(".pdf")


async def test_an_unsupported_type_is_refused_without_uploading() -> None:
    storage, http = FakeStorage(), FakeHttp()
    assert await _store("video/mp4", b"unos bytes", storage, http) is None
    assert http.puts == []


async def test_bytes_over_the_limit_are_refused_without_uploading() -> None:
    """El tamaño del sobre es una promesa del proveedor; esto es lo que la sostiene."""
    storage, http = FakeStorage(), FakeHttp()
    assert await _store("image/jpeg", b"x" * (MAX_MEDIA_BYTES + 1), storage, http) is None
    assert http.puts == []


async def test_empty_bytes_are_refused() -> None:
    storage, http = FakeStorage(), FakeHttp()
    assert await _store("image/jpeg", b"", storage, http) is None
    assert http.puts == []


async def test_storage_not_configured_returns_none_instead_of_raising() -> None:
    """Es un problema de despliegue, y no puede costarle el mensaje al cliente."""
    storage, http = FakeStorage(configured=False), FakeHttp()
    assert await _store("image/jpeg", b"unos bytes", storage, http) is None
    assert http.puts == []


async def test_a_failing_upload_returns_none_instead_of_raising() -> None:
    storage, http = FakeStorage(), FakeHttp(fail=True)
    assert await _store("image/jpeg", b"unos bytes", storage, http) is None
    # Se intentó: el fallo es de R2, no una decisión previa.
    assert len(http.puts) == 1
