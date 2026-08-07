"""assistant — derecho de uso, libro mayor de consumo y estado de conversación

Revision ID: 0028_assistant
Revises: 0027_alert_subject_label
Create Date: 2026-07-31 00:00:00.000000

El diseño del cambio llamaba a esta migración `0024_assistant`; ese número se lo llevó
`alert-notifications`, que se implementó antes. Es el mismo caso que ya pasó entre
`whatsapp-autoreply` (0023) y las alertas.

Tres tablas, todas de tenant:

- `assistant_entitlements` — lo que un tenant compró. **Nadie tiene fila**, así que al
  aplicar esto no se llama a ningún modelo ni una vez y todo lo anterior se comporta igual.
- `assistant_usage_ledger` — una fila por llamada, de sólo-añadir, con las dos capas de coste
  (lo que nos cobró el proveedor y lo que se le facturó al tenant). Sin `updated_at` a
  propósito: si las filas se pueden editar, "¿por qué me cobraste esto?" deja de tener
  respuesta. El índice `(tenant_id, occurred_at)` es el que mantiene barata la comprobación
  de saldo, que ocurre ANTES de cada llamada.
- `assistant_conversation_state` — la charla como la ve el asistente. Separada del hilo de
  WhatsApp porque el chat de administración no tiene hilo y porque el hilo humano lleva
  saludos y comprobantes por los que no queremos pagar tokens.

Sin backfill: no hay nada que rellenar hacia atrás.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_assistant"
down_revision: str | None = "0027_alert_subject_label"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("monthly_quota_units", sa.Integer(), nullable=False),
        sa.Column("period_anchor", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warning_threshold_percent", sa.Integer(), nullable=False),
        sa.Column("fallback_message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_assistant_entitlements_tenant"),
    )
    op.create_index(
        op.f("ix_assistant_entitlements_tenant_id"),
        "assistant_entitlements",
        ["tenant_id"],
    )

    op.create_table(
        "assistant_usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("caller_kind", sa.String(length=20), nullable=False),
        sa.Column("conversation_ref", sa.String(length=120), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("provider_cost", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("billed_units", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assistant_usage_ledger_tenant_id"),
        "assistant_usage_ledger",
        ["tenant_id"],
    )
    op.create_index(
        "ix_assistant_ledger_tenant_period",
        "assistant_usage_ledger",
        ["tenant_id", "occurred_at"],
    )

    op.create_table(
        "assistant_conversation_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_ref", sa.String(length=120), nullable=False),
        sa.Column("caller_kind", sa.String(length=20), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("turns", sa.JSON(), nullable=False),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "conversation_ref", name="uq_assistant_state_conversation"
        ),
    )
    op.create_index(
        op.f("ix_assistant_conversation_state_tenant_id"),
        "assistant_conversation_state",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_assistant_conversation_state_branch_id"),
        "assistant_conversation_state",
        ["branch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_assistant_conversation_state_branch_id"),
        table_name="assistant_conversation_state",
    )
    op.drop_index(
        op.f("ix_assistant_conversation_state_tenant_id"),
        table_name="assistant_conversation_state",
    )
    op.drop_table("assistant_conversation_state")
    op.drop_index(
        "ix_assistant_ledger_tenant_period", table_name="assistant_usage_ledger"
    )
    op.drop_index(
        op.f("ix_assistant_usage_ledger_tenant_id"),
        table_name="assistant_usage_ledger",
    )
    op.drop_table("assistant_usage_ledger")
    op.drop_index(
        op.f("ix_assistant_entitlements_tenant_id"),
        table_name="assistant_entitlements",
    )
    op.drop_table("assistant_entitlements")
