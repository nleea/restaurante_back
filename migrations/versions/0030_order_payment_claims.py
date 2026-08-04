"""order_payment_claims — lo que el cliente DICE que pagó, con su comprobante

Revision ID: 0030_order_payment_claims
Revises: 0029_order_edit_token
Create Date: 2026-07-31 00:00:00.000000

Tabla propia, y no una columna en `order_payments`, por una razón que es toda la decisión:
`payments_total` suma esa tabla, y de ella cuelgan la verificación de cocina, el cierre del
pedido, la caja y el arqueo. Una declaración del cliente ahí —aunque llevara `verified = false`—
haría que un pedido entrara a cocina porque alguien escribió que ya pagó, y obligaría a excluir
el estado nuevo en cada consulta de dinero del sistema. La primera que se olvidara sería un
descuadre.

Separadas, la propiedad se sostiene sola: **lo que no está en `order_payments` no es dinero en
ninguna pantalla.**

El índice va por pedido —la pregunta caliente es "¿este pedido tiene algo pendiente?", y se hace
cada vez que el personal abre una comanda—. El estado no entra en el índice a propósito: son
tres filas por pedido como mucho, así que filtrarlo en memoria no cuesta nada y ahorra un índice
que sería prefijo de otro.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_order_payment_claims"
down_revision: str | None = "0029_order_edit_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_payment_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("proof_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("resolved_by_employee_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_by_employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_payment_claims_order_id"), "order_payment_claims", ["order_id"]
    )
    op.create_index(
        op.f("ix_order_payment_claims_tenant_id"),
        "order_payment_claims",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_order_payment_claims_branch_id"),
        "order_payment_claims",
        ["branch_id"],
    )
    op.create_index(
        op.f("ix_order_payment_claims_resolved_by_employee_id"),
        "order_payment_claims",
        ["resolved_by_employee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_order_payment_claims_resolved_by_employee_id"),
        table_name="order_payment_claims",
    )
    op.drop_index(
        op.f("ix_order_payment_claims_branch_id"), table_name="order_payment_claims"
    )
    op.drop_index(
        op.f("ix_order_payment_claims_tenant_id"), table_name="order_payment_claims"
    )
    op.drop_index(
        op.f("ix_order_payment_claims_order_id"), table_name="order_payment_claims"
    )
    op.drop_table("order_payment_claims")
