"""whatsapp_faqs — las FAQs por palabra clave, en una columna JSON nullable

Revision ID: 0031_whatsapp_faqs
Revises: 0030_order_payment_claims
Create Date: 2026-08-01 00:00:00.000000

Una columna, y toda la decisión está en que sea **NULLABLE**: `NULL` y `[]` significan cosas
distintas y de eso depende que una FAQ borrada no resucite.

    NULL  → este tenant nunca las tocó. Se le ofrecen las cuatro sugeridas, APAGADAS.
    []    → decidió que ninguna. Se respeta y no se le ofrece nada.

Con un `NOT NULL DEFAULT '[]'` las dos situaciones serían indistinguibles, y la lectura tendría
que sembrar los valores de fábrica cada vez que encontrara la lista vacía — es decir, justo
después de que el dueño las borrara. Es el mismo bug que el `armed` sin fila de las alertas.

Los tenants existentes quedan en `NULL`, así que ven las sugeridas escritas y apagadas: instalar
esto no le cambia el canal a nadie sin que lo pida.

No hace falta tocar `whatsapp_outbound_emissions`: su unicidad vive en una sola columna de texto
(`dedupe_key`), así que la clave nueva —`faq:<conversación>:<id de la FAQ>`— entra sin columna
nueva. Una columna para el id de la FAQ sólo repetiría un trozo de la clave sin una FK detrás.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031_whatsapp_faqs"
down_revision: str | None = "0030_order_payment_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_autoreply_settings",
        sa.Column("faqs", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_autoreply_settings", "faqs")
