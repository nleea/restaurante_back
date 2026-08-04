"""whatsapp_channel — per-branch sessions, branch-scoped threads, idempotent inbound

Revision ID: 0021_whatsapp_channel
Revises: 0020_operating_hours
Create Date: 2026-07-30 00:00:00.000000

Turns the messaging schema from a sketch into a working channel:

- new `whatsapp_sessions`: one paired WhatsApp number per branch (instance reference,
  connection status, paired number) — never provider credentials.
- `branch_id` on `whatsapp_conversations` and `whatsapp_messages`, satisfying the binding
  rule that every business entity carries a branch from day 1. Created NOT NULL directly:
  the tables are empty, which is precisely why this is done now rather than later.
- `provider_message_id` on messages with `UNIQUE(tenant_id, provider_message_id)`, so the
  bridge's redeliveries collapse into one row instead of three.
- `delivery_state` for outbound reconciliation (`pending → sent | failed`). Inbound rows
  default to `sent`: they already arrived.
- conversation `status` default moves from `'bot'` to `'new'` — there is no bot yet.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_whatsapp_channel"
down_revision: str | None = "0020_operating_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("provider_instance_ref", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'disconnected'"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(length=30), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "branch_id", name="uq_whatsapp_sessions_tenant_branch"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_instance_ref",
            name="uq_whatsapp_sessions_tenant_instance_ref",
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_sessions_tenant_id"), "whatsapp_sessions", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_whatsapp_sessions_branch_id"), "whatsapp_sessions", ["branch_id"]
    )
    # The webhook resolves the session by instance ref before it knows the tenant.
    op.create_index(
        "ix_whatsapp_sessions_provider_instance_ref",
        "whatsapp_sessions",
        ["provider_instance_ref"],
    )

    # --- conversations: branch-scoped, default status 'new' ------------------
    op.add_column(
        "whatsapp_conversations", sa.Column("branch_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_whatsapp_conversations_branch_id",
        "whatsapp_conversations",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_whatsapp_conversations_branch_id"),
        "whatsapp_conversations",
        ["branch_id"],
    )
    op.create_index(
        "ix_whatsapp_conversations_branch_status",
        "whatsapp_conversations",
        ["branch_id", "status"],
    )
    op.alter_column(
        "whatsapp_conversations",
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'new'"),
        existing_nullable=False,
    )

    # --- messages: branch-scoped, idempotent, reconcilable -------------------
    op.add_column(
        "whatsapp_messages", sa.Column("branch_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_whatsapp_messages_branch_id",
        "whatsapp_messages",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_whatsapp_messages_branch_id"), "whatsapp_messages", ["branch_id"]
    )
    op.add_column(
        "whatsapp_messages",
        sa.Column("provider_message_id", sa.String(length=180), nullable=True),
    )
    op.create_unique_constraint(
        "uq_whatsapp_messages_tenant_provider_id",
        "whatsapp_messages",
        ["tenant_id", "provider_message_id"],
    )
    op.add_column(
        "whatsapp_messages",
        sa.Column(
            "delivery_state",
            sa.String(length=20),
            server_default=sa.text("'sent'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_whatsapp_messages_conversation_sent_at",
        "whatsapp_messages",
        ["whatsapp_conversation_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_messages_conversation_sent_at", table_name="whatsapp_messages"
    )
    op.drop_column("whatsapp_messages", "delivery_state")
    op.drop_constraint(
        "uq_whatsapp_messages_tenant_provider_id", "whatsapp_messages", type_="unique"
    )
    op.drop_column("whatsapp_messages", "provider_message_id")
    op.drop_index(op.f("ix_whatsapp_messages_branch_id"), table_name="whatsapp_messages")
    op.drop_constraint(
        "fk_whatsapp_messages_branch_id", "whatsapp_messages", type_="foreignkey"
    )
    op.drop_column("whatsapp_messages", "branch_id")

    op.alter_column(
        "whatsapp_conversations",
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'bot'"),
        existing_nullable=False,
    )
    op.drop_index(
        "ix_whatsapp_conversations_branch_status", table_name="whatsapp_conversations"
    )
    op.drop_index(
        op.f("ix_whatsapp_conversations_branch_id"), table_name="whatsapp_conversations"
    )
    op.drop_constraint(
        "fk_whatsapp_conversations_branch_id",
        "whatsapp_conversations",
        type_="foreignkey",
    )
    op.drop_column("whatsapp_conversations", "branch_id")

    op.drop_index(
        "ix_whatsapp_sessions_provider_instance_ref", table_name="whatsapp_sessions"
    )
    op.drop_index(op.f("ix_whatsapp_sessions_branch_id"), table_name="whatsapp_sessions")
    op.drop_index(op.f("ix_whatsapp_sessions_tenant_id"), table_name="whatsapp_sessions")
    op.drop_table("whatsapp_sessions")
