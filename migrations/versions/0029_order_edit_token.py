"""orders.edit_token — el enlace con el que el cliente edita su propio pedido

Revision ID: 0029_order_edit_token
Revises: 0028_assistant
Create Date: 2026-07-31 00:00:00.000000

El token es una **capacidad**: quien tenga la URL edita ese pedido. De ahí las dos decisiones
que se ven en el DDL:

- **Por pedido, no por contacto.** El token del chat (`whatsapp_conversations.store_token`)
  identifica a una persona, así que reenviar ese enlace daría acceso a *todos* sus pedidos.
  Uno por pedido acota el daño de un enlace compartido, y de paso sirve al cliente que pidió
  por la web y nunca escribió por WhatsApp.
- **Único GLOBAL, no por tenant.** Adivinar un token tiene que ser imposible, no improbable
  dentro de un negocio. El índice único también es el que hace barata la resolución, que
  ocurre en cada apertura del enlace.

Nace nulo en todo lo que ya existe, y sin token no hay vista: los pedidos anteriores a este
cambio simplemente no tienen enlace, que es el comportamiento correcto y no requiere relleno.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029_order_edit_token"
down_revision: str | None = "0028_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("edit_token", sa.String(length=64), nullable=True))
    op.add_column(
        "orders",
        sa.Column("edit_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_orders_edit_token"), "orders", ["edit_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_edit_token"), table_name="orders")
    op.drop_column("orders", "edit_token_expires_at")
    op.drop_column("orders", "edit_token")
