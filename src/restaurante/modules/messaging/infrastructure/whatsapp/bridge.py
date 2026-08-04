"""HTTP adapter for the unofficial WhatsApp bridge.

Implements `WhatsAppGateway` with exactly one verb. Everything bridge-specific — the
URL shape, the auth header, where the provider's message id hides in the response —
is confined to this file, so replacing the bridge (or moving to the official Cloud
API) is one new adapter and no changes anywhere else.

This adapter performs NO reachability check. That is deliberate: the check lives in
`GuardedWhatsAppGateway`, which is the only thing the composition root injects.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

import httpx

from restaurante.modules.messaging.domain.entities import WhatsAppSession
from restaurante.modules.messaging.domain.errors import (
    MediaUnavailableError,
    MessageDeliveryError,
)

logger = logging.getLogger(__name__)

# Where different bridges report the id of the message they just accepted. Tried in
# order so a bridge swap does not necessarily need a code change.
_MESSAGE_ID_KEYS = ("id", "messageId", "message_id", "key")


class BridgeWhatsAppGateway:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def send_text(
        self, session: WhatsAppSession, to_phone: str, body: str
    ) -> str:
        if not self._base_url:
            # Misconfiguration, not a transport failure — say which one it is.
            raise MessageDeliveryError(
                "El puente de WhatsApp no está configurado (WHATSAPP_BRIDGE_BASE_URL)."
            )

        # Evolution API v2: `POST /message/sendText/{instance}` con `{number, text}` y la
        # clave en la cabecera `apikey` (no Bearer). Leído de su código, no de memoria:
        # `src/api/routes/sendMessage.router.ts` y `src/api/dto/sendMessage.dto.ts`.
        url = f"{self._base_url}/message/sendText/{session.provider_instance_ref}"
        payload = {"number": to_phone, "text": body}
        headers = {"apikey": self._api_key} if self._api_key else {}

        try:
            if self._client is not None:
                response = await self._client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            # The bridge being down is expected often enough to be ordinary: log it,
            # translate it, and let the caller mark the message `failed`.
            logger.warning("WhatsApp bridge unreachable: %s", exc)
            raise MessageDeliveryError(
                "No se pudo contactar el puente de WhatsApp."
            ) from exc

        if response.status_code >= 400:
            logger.warning(
                "WhatsApp bridge rejected send: %s %s",
                response.status_code,
                response.text[:200],
            )
            raise MessageDeliveryError(
                f"El puente de WhatsApp rechazó el envío ({response.status_code})."
            )

        return _extract_message_id(_safe_json(response))


    async def send_media(
        self,
        session: WhatsAppSession,
        to_phone: str,
        data: bytes,
        *,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> str:
        """Evolution v2: `POST /message/sendMedia/{instance}`.

        El archivo va en base64 dentro del cuerpo y no como URL: nuestras URLs de R2 son públicas
        pero opacas, y hacer que el puente las descargue mete a un tercero —y su red— en medio de
        un envío que ya tenemos resuelto en memoria.

        `mediatype` es la familia (`image` / `document`), que es lo que Evolution usa para decidir
        cómo lo presenta WhatsApp; el `mimetype` exacto viaja aparte.
        """
        if not self._base_url:
            raise MessageDeliveryError(
                "El puente de WhatsApp no está configurado (WHATSAPP_BRIDGE_BASE_URL)."
            )
        payload = {
            "number": to_phone,
            "mediatype": "image" if mimetype.startswith("image/") else "document",
            "mimetype": mimetype,
            "media": base64.b64encode(data).decode(),
            "fileName": filename,
        }
        if caption:
            payload["caption"] = caption
        data_out = await self._request(
            "POST", f"/message/sendMedia/{session.provider_instance_ref}", json=payload
        )
        return _extract_message_id(data_out)

    async def fetch_media(
        self,
        session: WhatsAppSession,
        provider_message_id: str,
        remote_jid: str,
        *,
        from_me: bool = False,
    ) -> bytes:
        """Baja el archivo de un mensaje ya recibido.

        Evolution v2: `POST /chat/getBase64FromMediaMessage/{instance}` con
        `{message: {key: {id, remoteJid, fromMe}}}` y devuelve `{base64, mimetype, …}`.
        Se pide la clave entera porque es lo que el proveedor exige.

        **Se pide en vez de recibirlo en el webhook** (`webhook.base64` sigue en `False` al
        emparejar) por una razón concreta: el sobre del webhook ya trae el tipo y el tamaño,
        así que un video de 20 MB se rechaza sin descargarlo. Con `base64: true` los bytes
        viajarían siempre —a un endpoint público— para decidir después.
        """
        if not self._base_url:
            raise MediaUnavailableError(
                "El puente de WhatsApp no está configurado (WHATSAPP_BRIDGE_BASE_URL)."
            )
        try:
            data = await self._request(
                "POST",
                f"/chat/getBase64FromMediaMessage/{session.provider_instance_ref}",
                json={
                    "message": {
                        "key": {
                            "id": provider_message_id,
                            "remoteJid": remote_jid,
                            "fromMe": from_me,
                        }
                    }
                },
            )
        except MessageDeliveryError as exc:
            # El transporte se traduce a "no hay archivo": quien llama no está enviando
            # nada, así que un error de envío ahí sería mentira sobre lo que pasó.
            raise MediaUnavailableError(str(exc)) from exc

        encoded = data.get("base64")
        if not isinstance(encoded, str) or not encoded:
            # Lo más probable: el puente no conserva los mensajes y no puede devolver este.
            raise MediaUnavailableError(
                "El puente no devolvió el archivo del mensaje. Suele ser que la instancia "
                "no conserva los mensajes recibidos."
            )
        try:
            return base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise MediaUnavailableError(
                "El puente devolvió un archivo que no se pudo decodificar."
            ) from exc

    async def start_pairing(
        self, session: WhatsAppSession, webhook_url: str, webhook_secret: str
    ) -> str | None:
        """Deja la instancia lista para escanear y devuelve el QR como data-URI PNG.

        Tres pasos contra Evolution v2, en este orden por una razón: si el webhook no queda
        configurado ANTES de que el número se empareje, los primeros mensajes se pierden sin
        dejar rastro — llegan a WhatsApp y no van a ninguna parte.

        1. `POST /instance/create` — idempotente para nosotros: si ya existe, se ignora el
           conflicto y se sigue.
        2. `POST /webhook/set/{instance}` — apuntando a nuestro endpoint, con la cabecera
           del secreto. Evolution v2.3.7 sí reenvía cabeceras propias (`webhook.headers`).
        3. `GET /instance/connect/{instance}` — devuelve `{base64, code, pairingCode}`.

        Devuelve None cuando la instancia ya está conectada: no hay QR que escanear.
        """
        if not self._base_url:
            raise MessageDeliveryError(
                "El puente de WhatsApp no está configurado (WHATSAPP_BRIDGE_BASE_URL)."
            )
        ref = session.provider_instance_ref
        await self._request(
            "POST",
            "/instance/create",
            json={"instanceName": ref, "integration": "WHATSAPP-BAILEYS", "qrcode": True},
            # 403/409 = la instancia ya existe. Emparejar de nuevo es legítimo.
            tolerate=(400, 403, 409),
        )
        await self._request(
            "POST",
            f"/webhook/set/{ref}",
            json={
                "webhook": {
                    "enabled": True,
                    "url": webhook_url,
                    "headers": {"X-Webhook-Secret": webhook_secret},
                    "byEvents": False,
                    "base64": False,
                    # Sólo lo que sabemos manejar. Suscribirse a todo llenaría el log de
                    # eventos que ignoramos y multiplicaría el tráfico por nada.
                    #
                    # `MESSAGES_UPDATE` son los acuses (✓✓): sin él, un mensaje nuestro se queda
                    # en "enviado" para siempre y el agente no sabe si le llegó al cliente. Va
                    # aquí y no en un ajuste porque no es una preferencia — es cómo funciona el
                    # canal. **Un número vinculado antes de esto no lo recibe hasta que se vuelva
                    # a vincular**; `/webhook/set` es idempotente y no desconecta, así que volver
                    # a pulsar Vincular basta.
                    "events": [
                        "MESSAGES_UPSERT",
                        "MESSAGES_UPDATE",
                        "CONNECTION_UPDATE",
                        "QRCODE_UPDATED",
                    ],
                }
            },
        )
        data = await self._request("GET", f"/instance/connect/{ref}")
        # Ya conectada: `connect` devuelve el estado, no un QR.
        qr = data.get("base64")
        if isinstance(qr, str) and qr:
            return qr
        nested = data.get("qrcode")
        if isinstance(nested, dict):
            candidate = nested.get("base64")
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    async def connection_state(self, session: WhatsAppSession) -> str | None:
        """El estado que reporta el puente: `open`, `connecting` o `close`."""
        if not self._base_url:
            return None
        data = await self._request(
            "GET", f"/instance/connectionState/{session.provider_instance_ref}"
        )
        instance = data.get("instance")
        if isinstance(instance, dict):
            state = instance.get("state")
            if isinstance(state, str):
                return state
        return None

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        tolerate: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {"apikey": self._api_key} if self._api_key else {}
        try:
            if self._client is not None:
                response = await self._client.request(
                    method, url, json=json, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(
                        method, url, json=json, headers=headers
                    )
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp bridge unreachable (%s %s): %s", method, path, exc)
            raise MessageDeliveryError(
                "No se pudo contactar el puente de WhatsApp."
            ) from exc
        if response.status_code >= 400 and response.status_code not in tolerate:
            logger.warning(
                "WhatsApp bridge rejected %s %s: %s %s",
                method,
                path,
                response.status_code,
                response.text[:200],
            )
            raise MessageDeliveryError(
                f"El puente de WhatsApp respondió {response.status_code}."
            )
        return _safe_json(response)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_message_id(data: dict[str, Any]) -> str:
    """Best-effort id extraction.

    A send the bridge accepted but whose id we cannot read is still a delivered
    message — returning empty would look like a failure. The caller stores whatever
    comes back; an empty id only costs us the ability to correlate a later receipt.
    """
    for key in _MESSAGE_ID_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("id")
            if isinstance(nested, str) and nested:
                return nested
    return ""
