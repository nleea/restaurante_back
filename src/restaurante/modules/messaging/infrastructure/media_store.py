"""Guardar en R2 el archivo de un mensaje de la conversación.

Reusa el mecanismo que ya existe para el comprobante del checkout
(`orders/infrastructure/payment_proof.py`): firmar un PUT **contra nosotros mismos** con
`StorageGateway.presign_put` y subir los bytes por httpx. Sin boto3, sin credenciales fuera del
servidor, y sin código de firma nuevo.

La clave lleva tenant y conversación por el mismo motivo que allí lleva tenant y pedido: un objeto
suelto en el bucket tiene que poder atribuirse sin consultar la base, y borrar lo de una
conversación tiene que ser un prefijo.

La URL resultante es **pública y opaca** — un uuid impredecible en la clave. Es privacidad por
opacidad, no por permisos, exactamente el trato que ya tienen los comprobantes. Se deja dicho aquí
porque una foto que alguien manda por su chat *se siente* más privada que un comprobante que subió
a propósito, y la propiedad técnica es la misma. Si algún día hay que cerrarlo, se cierra para los
dos a la vez y es un change propio.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx

from restaurante.modules.messaging.domain.media import STORABLE_MIMES, fits
from restaurante.shared.storage.ports import StorageGateway

logger = logging.getLogger(__name__)


async def store_conversation_media(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    mimetype: str,
    data: bytes,
    *,
    storage: StorageGateway,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Sube el archivo y devuelve su URL pública, o `None` si no se pudo guardar.

    Sirve para los dos sentidos: el archivo de un mensaje no cambia de naturaleza según quién lo
    mandó, y el prefijo de la clave es el mismo (la conversación).

    **Nunca levanta**: quien llama acaba de guardar el mensaje y lo único que está en juego aquí
    es el archivo. Un `None` deja el hilo diciendo que hay algo que no se pudo traer, que es la
    verdad y es depurable; una excepción costaría el mensaje.
    """
    extension = STORABLE_MIMES.get(mimetype)
    if extension is None:
        logger.warning("Archivo con tipo no soportado: %s", mimetype)
        return None
    if not fits(data):
        logger.warning(
            "Archivo fuera de tope (%s bytes); el sobre prometía otra cosa",
            len(data),
        )
        return None
    if not storage.is_configured:
        # Misma frase que el comprobante del checkout, a propósito: es el mismo problema de
        # despliegue y quien lo lea en el log tiene que reconocerlo.
        logger.warning(
            "El almacenamiento de archivos no está configurado; el archivo no se guarda."
        )
        return None

    key = f"whatsapp-media/{tenant_id}/{conversation_id}/{uuid.uuid4().hex}{extension}"
    upload_url = storage.presign_put(key, now=now or datetime.now(UTC))
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await client.put(
            upload_url, content=data, headers={"Content-Type": mimetype}
        )
        response.raise_for_status()
    except Exception:  # noqa: BLE001 - el archivo no puede costar el mensaje
        logger.warning("No se pudo subir el archivo a R2", exc_info=True)
        return None
    finally:
        if owns_client:
            await client.aclose()
    return storage.public_url(key)
