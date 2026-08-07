"""order_refunds — dinero que le debemos al cliente por un domicilio no entregado

Revision ID: 0022_order_refunds
Revises: 0021_whatsapp_channel
Create Date: 2026-07-30 00:00:00.000000

Una obligación de devolver nace cuando una entrega se marca no entregada y su pedido ya
tenía pagos. Guarda el método por el que ENTRÓ la plata, porque es por el que tiene que
salir: confirmarla crea un movimiento de caja de salida con ese mismo método, nunca
efectivo. Lo prepagado nunca tocó el cajón, y registrarlo como efectivo haría que el
sistema esperara menos plata de la que hay — rompería el arqueo justo al cuadrarlo.

`UNIQUE(order_id)`: una devolución por pedido, así marcar dos veces no duplica la deuda.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_order_refunds"
down_revision: str | None = "0021_whatsapp_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("resolved_by_employee_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_order_refunds_order"),
    )
    op.create_index(op.f("ix_order_refunds_tenant_id"), "order_refunds", ["tenant_id"])
    op.create_index(op.f("ix_order_refunds_branch_id"), "order_refunds", ["branch_id"])
    op.create_index(op.f("ix_order_refunds_order_id"), "order_refunds", ["order_id"])
    op.create_index(op.f("ix_order_refunds_status"), "order_refunds", ["status"])
    op.create_index(
        op.f("ix_order_refunds_resolved_by_employee_id"),
        "order_refunds",
        ["resolved_by_employee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_order_refunds_resolved_by_employee_id"), table_name="order_refunds"
    )
    op.drop_index(op.f("ix_order_refunds_status"), table_name="order_refunds")
    op.drop_index(op.f("ix_order_refunds_order_id"), table_name="order_refunds")
    op.drop_index(op.f("ix_order_refunds_branch_id"), table_name="order_refunds")
    op.drop_index(op.f("ix_order_refunds_tenant_id"), table_name="order_refunds")
    op.drop_table("order_refunds")
