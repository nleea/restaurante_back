"""greeting_awaiting_payment — la tercera variante del saludo

Revision ID: 0033_greeting_awaiting_payment
Revises: 0032_whatsapp_message_media
Create Date: 2026-08-01 00:00:00.000000

Una columna de texto para el saludo de quien tiene un pedido prepago sin pagar. Se elige por el
ESTADO del pedido y nunca por lo que el cliente escribió — el saludo sigue sin leer el texto, que
es la regla #1 del módulo.

`NOT NULL DEFAULT ''` y no nullable, al contrario que las FAQs: aquí vacío y "sin configurar"
significan lo mismo —usa la variante de abierto/cerrado—, así que no hay una tercera situación que
distinguir. En las FAQs sí la había ("nunca las tocó" frente a "decidió que ninguna") y por eso esa
columna es nullable.

Los tenants existentes quedan con la cadena vacía, así que su saludo sigue siendo exactamente el de
hoy: esta variante no sale hasta que el dueño escriba el texto.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033_greeting_awaiting_payment"
down_revision: str | None = "0032_whatsapp_message_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_autoreply_settings",
        sa.Column(
            "greeting_awaiting_payment_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_autoreply_settings", "greeting_awaiting_payment_text")
