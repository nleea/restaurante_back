"""Menú de opciones de WhatsApp — la respuesta que evita el silencio en un chat abierto

Revision ID: 0048_whatsapp_options_menu
Revises: 0047_whatsapp_scheduled_statuses
Create Date: 2026-09-21 00:00:00.000000

Dos columnas para el menú de opciones: el interruptor y el texto. Existe porque una conversación
`greeted` a la que el saludo, el asistente y las FAQs no contestan se quedaba muda, y al cliente
eso le parece que lo ignoran.

`menu_enabled` nace `false` y `menu_text` nace vacío, la misma postura que el saludo y las FAQs:
instalar esto no puede cambiarle el canal a nadie. Un tenant que lo encienda sin escribir texto
recibe el de fábrica. `NOT NULL` en las dos: vacío y "sin configurar" significan lo mismo —usa el
texto de fábrica—, así que no hay una tercera situación que distinguir.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0048_whatsapp_options_menu"
down_revision: str | None = "0047_whatsapp_scheduled_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_autoreply_settings",
        sa.Column(
            "menu_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "whatsapp_autoreply_settings",
        sa.Column(
            "menu_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_autoreply_settings", "menu_text")
    op.drop_column("whatsapp_autoreply_settings", "menu_enabled")
