"""Errores propios del storefront público."""

from __future__ import annotations

from restaurante.modules.storefront.domain.order_edit import EditRefusal
from restaurante.shared.domain.errors import ConflictError


class OrderEditRefused(ConflictError):
    """Un no con motivo, para que el front diga una frase y no "algo salió mal".

    El motivo viaja en el cuerpo (`refusal`) además de en la frase: el front tiene que poder
    reaccionar distinto —apagar la vista entera, marcar una línea, ofrecer una persona— y para
    eso necesita un código, no un texto que alguien reescribirá.

    Vive en el dominio y no junto al caso de uso para que `shared.api.errors` pueda mapearla
    sin arrastrar la aplicación entera al arranque, igual que hacen alerts y messaging.
    """

    code = "order_edit_refused"

    def __init__(self, refusal: EditRefusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = str(refusal)

    def payload(self) -> dict[str, object]:
        return {"refusal": self.refusal}
