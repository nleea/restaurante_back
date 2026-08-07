"""Domain errors of the messaging module.

Each one exists because the API must say something specific: a mute branch, a
conversation somebody else already took, or a send that would open an unsolicited
conversation. Mapped to HTTP in `shared/api/errors.py`.
"""

from __future__ import annotations

from restaurante.shared.domain.errors import DomainError


class SessionNotFoundError(DomainError):
    """No WhatsApp session matches the branch or provider instance reference.

    Its own code rather than `not_found`: for the webhook it means "this instance is
    not ours", and for the inbox it means "this branch has no number paired yet" —
    a state the sessions screen must offer to fix, not a missing record.
    """

    code = "whatsapp_session_not_found"


class ConversationAlreadyClaimedError(DomainError):
    """Another employee claimed the conversation first.

    Carries the holder so the API can name them: telling an agent "already taken"
    without saying by whom leaves them with nothing to do about it.
    """

    code = "conversation_already_claimed"

    def __init__(
        self,
        holder_employee_id: str | None = None,
        holder_name: str | None = None,
    ) -> None:
        who = holder_name or "otro empleado"
        super().__init__(f"La conversación ya fue tomada por {who}.")
        self.holder_employee_id = holder_employee_id
        self.holder_name = holder_name

    def payload(self) -> dict[str, object]:
        return {
            "holder_employee_id": self.holder_employee_id,
            "holder_name": self.holder_name,
        }


class ContactNotReachableError(DomainError):
    """The outbound guard refused: this phone never wrote to us.

    We never initiate a conversation — that is what gets a number banned. Raised by
    the gateway itself, so no caller can forget the check.
    """

    code = "contact_not_reachable"


class MessageDeliveryError(DomainError):
    """The bridge rejected the send or was unreachable.

    The message stays in the thread marked `failed`; the agent must learn that their
    reply did not land.
    """

    code = "message_delivery_failed"


class MediaUnavailableError(DomainError):
    """El puente no devolvió el archivo de un mensaje entrante.

    Su propio error y no `MessageDeliveryError` porque no es un envío: aquí no hay nada
    que se le haya prometido a nadie. Quien lo recibe se lo traga —el mensaje ya está
    guardado— y el hilo queda diciendo que llegó un archivo y no se pudo traer.

    La causa más probable no es la red: es que Evolution esté configurado sin conservar
    los mensajes, así que no puede devolver el que le pedimos. Por eso el mensaje de
    error lo dice con esas palabras en vez de con un stack trace.
    """

    code = "whatsapp_media_unavailable"
