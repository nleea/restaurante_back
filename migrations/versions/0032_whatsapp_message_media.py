"""whatsapp_message_media — el archivo de un mensaje entrante, y la clave para pedirlo

Revision ID: 0032_whatsapp_message_media
Revises: 0031_whatsapp_faqs
Create Date: 2026-08-01 00:00:00.000000

Cuatro columnas, todas nullable, y cada una responde a algo distinto:

    provider_remote_jid  la dirección del proveedor TAL CUAL llegó. Hace falta para pedirle
                         después el archivo: exige la clave entera (`{id, remoteJid, fromMe}`),
                         no sólo el id. Se guarda en vez de reconstruirla del teléfono porque
                         los JID de WhatsApp tienen más de una forma (`@s.whatsapp.net`, `@lid`)
                         y esa reconstrucción ya fue una de las trampas de la integración.
    media_type           `image` / `document`, **aunque el archivo no se haya guardado**. Es lo
                         que permite que el hilo diga "llegó una imagen" cuando el puente no la
                         devolvió, en vez de un hueco sin explicación.
    media_mime           el tipo exacto, para servir el archivo y para saber si es un PDF.
    media_url            la URL pública y opaca en R2. Nula cuando no se guardó — por tipo, por
                         tamaño, o porque el puente no lo devolvió.

`media_type` sin `media_url` es un estado legítimo y deliberado: significa "llegó un archivo y no
se pudo traer". Los mensajes que ya existen quedan con las cuatro en NULL, que es exactamente lo
que son: mensajes de texto.

Sin índices nuevos: nada consulta por estas columnas — se leen con el mensaje, que ya se busca por
conversación y fecha.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_whatsapp_message_media"
down_revision: str | None = "0031_whatsapp_faqs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_messages",
        sa.Column("provider_remote_jid", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "whatsapp_messages", sa.Column("media_type", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "whatsapp_messages",
        sa.Column("media_mime", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "whatsapp_messages", sa.Column("media_url", sa.String(length=512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("whatsapp_messages", "media_url")
    op.drop_column("whatsapp_messages", "media_mime")
    op.drop_column("whatsapp_messages", "media_type")
    op.drop_column("whatsapp_messages", "provider_remote_jid")
