"""Guardar el comprobante que manda el cliente. Valida primero, sube después.

Los bytes pasan POR la API en vez de ir con una URL prefirmada, y es la decisión deliberada del
cambio: una firma autoriza un PUT pero **no acota cuántos bytes se meten**, y esta puerta es
pública —cualquiera con un enlace vivo—. Comprobando aquí, el límite es real; con la firma sería
una intención.

El archivo acaba igual en R2: se reusa la misma firma que ya existe (`presign_put`) contra
nosotros mismos. Sin código de firma nuevo, sin boto3, y las credenciales sin salir del servidor.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx

from restaurante.shared.domain.errors import ValidationError
from restaurante.shared.storage.ports import StorageGateway

#: Lo que una foto de un comprobante puede ser. PDF entra porque los bancos lo mandan así.
PROOF_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

#: 5 MB. Un comprobante es una captura de pantalla; lo que pase de aquí no es un comprobante.
MAX_PROOF_BYTES = 5 * 1024 * 1024


async def store_payment_proof(
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    content_type: str,
    data: bytes,
    *,
    storage: StorageGateway,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Sube el comprobante y devuelve su URL pública. Valida ANTES de escribir nada.

    La clave lleva tenant y pedido: un objeto suelto en el bucket tiene que poder atribuirse sin
    consultar la base, y borrar lo de un pedido tiene que ser un prefijo.
    """
    if content_type not in PROOF_TYPES:
        raise ValidationError(
            "El comprobante debe ser una imagen (PNG, JPG, WEBP) o un PDF."
        )
    if not data:
        raise ValidationError("El comprobante llegó vacío.")
    if len(data) > MAX_PROOF_BYTES:
        raise ValidationError("El comprobante pesa demasiado (máximo 5 MB).")
    if not storage.is_configured:
        raise ValidationError("El almacenamiento de archivos no está configurado.")

    key = f"payment-proofs/{tenant_id}/{order_id}/{uuid.uuid4().hex}{PROOF_TYPES[content_type]}"
    upload_url = storage.presign_put(key, now=now or datetime.now(UTC))
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await client.put(
            upload_url, content=data, headers={"Content-Type": content_type}
        )
        response.raise_for_status()
    finally:
        if owns_client:
            await client.aclose()
    return storage.public_url(key)
