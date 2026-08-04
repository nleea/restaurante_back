"""whatsapp_autoreply — saludo automático, enlace con token y avisos de estado

Revision ID: 0023_whatsapp_autoreply
Revises: 0022_order_refunds
Create Date: 2026-07-30 00:00:00.000000

Tres piezas, todas apagadas por defecto — instalar esto no cambia el comportamiento de
ningún tenant hasta que alguien lo encienda:

- `whatsapp_conversations` gana `store_token` + `store_token_expires_at`: una capability URL
  opaca que resuelve a un CONTACTO (nunca a un pedido), reutilizable mientras viva y con
  vencimiento. Único por tenant.
- `whatsapp_outbound_emissions`: la marca de "esto ya salió". Existe sólo por su constraint
  de unicidad — un `if last_sent_at is None` es una carrera entre dos workers, y la base de
  datos no lo es.
- `whatsapp_autoreply_settings`: una fila por tenant con el saludo, la ventana de
  inactividad y qué transiciones le hablan al cliente.

`orders.whatsapp_contact_id` NO se toca: ya existía antes de este change.

Los estados `greeted` y `bot` de las conversaciones no necesitan DDL — `status` es un
String(20) sin constraint; el conjunto válido vive en el código.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_whatsapp_autoreply"
down_revision: str | None = "0022_order_refunds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- El enlace con token, sobre la conversación --------------------------
    op.add_column(
        "whatsapp_conversations",
        sa.Column("store_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "whatsapp_conversations",
        sa.Column("store_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_whatsapp_conversations_tenant_store_token",
        "whatsapp_conversations",
        ["tenant_id", "store_token"],
    )

    # --- Emitir una sola vez -------------------------------------------------
    op.create_table(
        "whatsapp_outbound_emissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        # La clave de deduplicación, ya compuesta: `greeting:<conv>` / `status:<pedido>:<estado>`.
        # Va en UNA columna y no en la tupla porque dos NULL no son iguales en SQL: con la
        # tupla, un aviso de estado (sin conversación) sería único consigo mismo y saldría
        # en cada rebote de la entrega.
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("customer_state", sa.String(length=40), nullable=True),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["whatsapp_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # LA razón de ser de la tabla: quien gane esta inserción es quien envía.
        sa.UniqueConstraint(
            "tenant_id", "dedupe_key", name="uq_whatsapp_emissions_key"
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_outbound_emissions_tenant_id"),
        "whatsapp_outbound_emissions",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_whatsapp_outbound_emissions_branch_id"),
        "whatsapp_outbound_emissions",
        ["branch_id"],
    )
    op.create_index(
        op.f("ix_whatsapp_outbound_emissions_conversation_id"),
        "whatsapp_outbound_emissions",
        ["conversation_id"],
    )
    op.create_index(
        op.f("ix_whatsapp_outbound_emissions_order_id"),
        "whatsapp_outbound_emissions",
        ["order_id"],
    )

    # --- Ajustes por tenant --------------------------------------------------
    op.create_table(
        "whatsapp_autoreply_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "greeting_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "greeting_open_text", sa.Text(), server_default=sa.text("''"), nullable=False
        ),
        sa.Column(
            "greeting_closed_text",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "assistant_offer_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "idle_hours", sa.Integer(), server_default=sa.text("24"), nullable=False
        ),
        sa.Column(
            "token_lifetime_hours",
            sa.Integer(),
            server_default=sa.text("24"),
            nullable=False,
        ),
        sa.Column(
            "status_mapping", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_whatsapp_autoreply_settings_tenant"),
    )
    op.create_index(
        op.f("ix_whatsapp_autoreply_settings_tenant_id"),
        "whatsapp_autoreply_settings",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_whatsapp_autoreply_settings_tenant_id"),
        table_name="whatsapp_autoreply_settings",
    )
    op.drop_table("whatsapp_autoreply_settings")

    for index in (
        "ix_whatsapp_outbound_emissions_order_id",
        "ix_whatsapp_outbound_emissions_conversation_id",
        "ix_whatsapp_outbound_emissions_branch_id",
        "ix_whatsapp_outbound_emissions_tenant_id",
    ):
        op.drop_index(op.f(index), table_name="whatsapp_outbound_emissions")
    op.drop_table("whatsapp_outbound_emissions")

    op.drop_constraint(
        "uq_whatsapp_conversations_tenant_store_token",
        "whatsapp_conversations",
        type_="unique",
    )
    op.drop_column("whatsapp_conversations", "store_token_expires_at")
    op.drop_column("whatsapp_conversations", "store_token")
