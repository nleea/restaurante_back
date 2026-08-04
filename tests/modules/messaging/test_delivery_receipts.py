"""La escala de los acuses, sin levantar la app.

Lo que se prueba aquí ES el change: que un acuse tardío no pueda apagar una palomita ya ganada.
Que las palomitas salgan en la pantalla es lo fácil; que no parpadeen es lo que hay que sostener.
"""

from __future__ import annotations

import pytest

from restaurante.modules.messaging.domain.delivery import (
    DELIVERY_RANK,
    advance,
    state_from_provider,
)
from restaurante.modules.messaging.infrastructure.api.schemas import (
    WebhookMessagePayload,
    delivery_update,
)
from restaurante.modules.messaging.infrastructure.models import MESSAGE_DELIVERY_STATES


class TestScale:
    def test_the_scale_climbs_in_the_expected_order(self) -> None:
        assert (
            DELIVERY_RANK["pending"]
            < DELIVERY_RANK["sent"]
            < DELIVERY_RANK["delivered"]
            < DELIVERY_RANK["read"]
        )

    def test_failed_is_not_a_step(self) -> None:
        """Está fuera de la escala a propósito: es el otro final, no un escalón."""
        assert "failed" not in DELIVERY_RANK

    def test_every_scale_state_is_a_declared_state(self) -> None:
        assert set(DELIVERY_RANK) <= set(MESSAGE_DELIVERY_STATES)


class TestAdvance:
    @pytest.mark.parametrize(
        ("current", "incoming", "expected"),
        [
            ("pending", "sent", "sent"),
            ("sent", "delivered", "delivered"),
            ("delivered", "read", "read"),
        ],
    )
    def test_each_step_climbs(self, current: str, incoming: str, expected: str) -> None:
        assert advance(current, incoming) == expected

    def test_a_late_lower_report_does_not_downgrade(self) -> None:
        """El corazón del change: `read` + un `delivered` tardío sigue siendo `read`.

        Los dos acuses salen de WhatsApp con milisegundos de diferencia y el puente los reenvía
        con sus propios reintentos, así que llegan desordenados con regularidad.
        """
        assert advance("read", "delivered") == "read"
        assert advance("read", "sent") == "read"
        assert advance("delivered", "sent") == "delivered"

    def test_the_same_report_twice_changes_nothing(self) -> None:
        assert advance("delivered", "delivered") == "delivered"
        assert advance("read", "read") == "read"

    def test_a_skipped_step_is_allowed(self) -> None:
        """Pasa de verdad: con el chat abierto, entregado y leído se funden en uno."""
        assert advance("sent", "read") == "read"
        assert advance("pending", "read") == "read"

    def test_a_failed_message_is_not_revived(self) -> None:
        """`failed` = no lo aceptó el puente, así que nunca tuvo id y nada puede emparejar."""
        assert advance("failed", "delivered") == "failed"
        assert advance("failed", "read") == "failed"

    def test_an_unknown_incoming_state_is_ignored(self) -> None:
        assert advance("sent", "whatever") == "sent"

    def test_it_never_returns_failed_from_a_live_message(self) -> None:
        assert advance("sent", "failed") == "sent"


class TestProviderStates:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("DELIVERY_ACK", "delivered"),
            ("READ", "read"),
            # Audio escuchado. Es leído: un tercer estado no le cambia la decisión a nadie.
            ("PLAYED", "read"),
            ("SERVER_ACK", "sent"),
            ("PENDING", "sent"),
        ],
    )
    def test_the_providers_values_translate(self, status: str, expected: str) -> None:
        assert state_from_provider(status) == expected

    def test_error_is_not_our_failed(self) -> None:
        """`failed` significa "el puente no lo aceptó" y es accionable. Un `ERROR` posterior no."""
        assert state_from_provider("ERROR") is None

    def test_an_unknown_value_is_silence(self) -> None:
        assert state_from_provider("SOMETHING_NEW") is None
        assert state_from_provider("") is None

    def test_server_ack_over_sent_is_a_no_op(self) -> None:
        """Es el valor por defecto del puente cuando NO sabe, así que tiene que ser inofensivo."""
        translated = state_from_provider("SERVER_ACK")
        assert translated is not None
        assert advance("sent", translated) == "sent"
        assert advance("read", translated) == "read"


# --- El sobre del puente -----------------------------------------------------
# Se prueba contra el sobre REAL de Evolution v2.3.7, tal y como lo construye
# `whatsapp.baileys.service.ts` — `{keyId, remoteJid, fromMe, status, instanceId}` — y no contra
# uno inventado. Un espejo inventado pasa siempre y no prueba nada.
def envelope(**over: object) -> WebhookMessagePayload:
    data: dict[str, object] = {
        "keyId": "3EB0C1D2E3F4",
        "remoteJid": "573001112233@s.whatsapp.net",
        "fromMe": True,
        "status": "DELIVERY_ACK",
        "instanceId": "b7d1…",
    }
    data.update(over)
    return WebhookMessagePayload(event="messages.update", data=data)


class TestEnvelope:
    def test_a_real_update_is_recognised(self) -> None:
        report = delivery_update(envelope())
        assert report is not None
        assert report.provider_message_id == "3EB0C1D2E3F4"
        assert report.state == "delivered"

    def test_read_translates(self) -> None:
        report = delivery_update(envelope(status="READ"))
        assert report is not None and report.state == "read"

    def test_a_report_about_the_customers_message_is_not_ours(self) -> None:
        """El evento viaja igual para los mensajes del cliente, y ésos no llevan palomitas."""
        assert delivery_update(envelope(fromMe=False)) is None

    def test_a_missing_from_me_is_not_ours_either(self) -> None:
        """Ausente no es `True`. Ante la duda, no es nuestro."""
        payload = WebhookMessagePayload(
            event="messages.update",
            data={"keyId": "3EB0", "status": "READ"},
        )
        assert delivery_update(payload) is None

    def test_message_id_serves_when_key_id_is_missing(self) -> None:
        """El puente lo manda cuando además encontró el mensaje en su propia base."""
        payload = WebhookMessagePayload(
            event="messages.update",
            data={"messageId": "abc", "fromMe": True, "status": "READ"},
        )
        report = delivery_update(payload)
        assert report is not None and report.provider_message_id == "abc"

    def test_without_an_id_there_is_nothing_to_match(self) -> None:
        assert delivery_update(envelope(keyId="")) is None

    def test_an_error_status_is_silence(self) -> None:
        assert delivery_update(envelope(status="ERROR")) is None

    def test_another_event_is_not_a_report(self) -> None:
        payload = WebhookMessagePayload(
            event="messages.upsert", data={"keyId": "x", "fromMe": True, "status": "READ"}
        )
        assert delivery_update(payload) is None

    def test_a_connection_update_is_not_a_report(self) -> None:
        payload = WebhookMessagePayload(
            event="connection.update", data={"state": "open"}
        )
        assert delivery_update(payload) is None
