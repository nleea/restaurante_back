"""alerts — reglas configuradas y alertas con ciclo de vida

Revision ID: 0024_alerts
Revises: 0023_whatsapp_autoreply
Create Date: 2026-07-30 00:00:00.000000

Dos tablas, y la forma de sus constraints ES el diseño:

- `alert_rules`: una regla por (tenant, sucursal, clave). Se siembran APAGADAS, así que
  instalar esto no hace que nadie reciba nada hasta que lo encienda. Encenderla en una
  sucursal no la enciende en las demás.
- `alerts`: una instancia disparada sobre un sujeto (`subject_ref`: el ingrediente, la
  sesión de WhatsApp o la de caja). Lleva un índice único **parcial** limitado a las
  alertas abiertas — es lo que garantiza "avisar una vez" desde la base de datos y no desde
  un `if ya_avisamos`, que es una carrera entre el job y el barrido.

  Parcial y no total porque las resueltas se conservan: "cuántas veces nos quedamos sin
  tomate" es el informe que alguien va a pedir, y dos episodios del mismo tomate son dos
  filas legítimas.

El estado `armed` no tiene fila: una alerta armada es la AUSENCIA de una abierta para ese
sujeto. Guardarlo obligaría a crear una fila por cada ingrediente de cada sucursal antes de
que pasara nada.

Sin backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_alerts"
down_revision: str | None = "0023_whatsapp_autoreply"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPEN_STATUSES = "status IN ('fired', 'acknowledged')"


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=60), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        # Nullable y con significado por regla: la de stock bajo NO lo usa (reutiliza el
        # `min_stock` de inventario), la de caja abierta lo lee como una hora del día.
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "recovery_buffer", sa.Float(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "escalation_after_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "escalate_to_whatsapp",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "branch_id", "rule_key", name="uq_alert_rules_branch_key"
        ),
    )
    op.create_index("ix_alert_rules_tenant_id", "alert_rules", ["tenant_id"])
    op.create_index("ix_alert_rules_branch_id", "alert_rules", ["branch_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=60), nullable=False),
        sa.Column("subject_ref", sa.String(length=120), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="fired"
        ),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        # El empleado que la tomó puede irse del negocio; la alerta sigue siendo un hecho.
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_branch_id", "alerts", ["branch_id"])
    op.create_index("ix_alerts_branch_status", "alerts", ["branch_id", "status"])
    # Como mucho UNA alerta abierta por sujeto. Esto es la garantía de "avisar una vez".
    op.create_index(
        "uq_alerts_open_subject",
        "alerts",
        ["tenant_id", "branch_id", "rule_key", "subject_ref"],
        unique=True,
        postgresql_where=sa.text(_OPEN_STATUSES),
        sqlite_where=sa.text(_OPEN_STATUSES),
    )


def downgrade() -> None:
    op.drop_index("uq_alerts_open_subject", table_name="alerts")
    op.drop_index("ix_alerts_branch_status", table_name="alerts")
    op.drop_index("ix_alerts_branch_id", table_name="alerts")
    op.drop_index("ix_alerts_tenant_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_alert_rules_branch_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_tenant_id", table_name="alert_rules")
    op.drop_table("alert_rules")
