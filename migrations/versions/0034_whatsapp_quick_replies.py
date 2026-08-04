"""quick_replies — las plantillas que un empleado inserta en el compositor

Revision ID: 0034_whatsapp_quick_replies
Revises: 0033_greeting_awaiting_payment
Create Date: 2026-08-01 00:00:00.000000

Una columna JSON con la lista de respuestas rápidas del tenant.

**No es un automatismo**, pese al nombre de la tabla: nada de esta columna se envía solo. Vive en
`whatsapp_autoreply_settings` porque ésa ya es la fila de "cómo habla este negocio por WhatsApp",
ya es una por tenant y ya se lee y se escribe entera; una tabla propia con `position` habría
convertido el reordenar en N updates y guardado dos verdades (el índice y el orden).

**Nullable a propósito, y `NULL` no es `[]`** — misma regla que `faqs`, misma razón: `NULL` es
"este tenant nunca las tocó" y `[]` es "decidió que ninguna". Sin la distinción, borrarlas todas y
no haberlas configurado nunca son el mismo valor, y las sugeridas resucitarían en el siguiente
render sobre una decisión explícita del dueño.

Sin backfill y sin `server_default`: los tenants existentes nacen en `NULL`, que es exactamente lo
que son. A diferencia de las FAQs, sembrar aquí no cambiaría el comportamiento de nadie —una
plantilla que nadie toca no manda nada—, pero las sugeridas se ofrecen en el editor y no se
guardan solas, así que tampoco hace falta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034_whatsapp_quick_replies"
down_revision: str | None = "0033_greeting_awaiting_payment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_autoreply_settings",
        sa.Column("quick_replies", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Revertir pierde las plantillas y nada más: ningún flujo depende de ellas y ningún mensaje
    # se deja de mandar por no tenerlas.
    op.drop_column("whatsapp_autoreply_settings", "quick_replies")
