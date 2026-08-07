"""La cuenta de mesa: agrupar varias comandas para cobrarlas en un gesto.

`qr-table-ordering` puso varias comandas vivas en una misma mesa, una por comensal. Cobrarlas
era imposible en un gesto: `order_payments` cuelga de un `order_id` y `close_order` exige que
los pagos de ESA comanda cubran SU total, así que "todo junto" —lo que pasa en casi todas las
mesas— no tenía dónde vivir.

`table_bills` es un AGRUPADOR, no una primitiva de dinero: no guarda saldo. La única verdad de
si una comanda está pagada sigue siendo `order_payments`, de donde ya cuelgan el cierre, el
arqueo, el reporte Z y las devoluciones. Por eso `close_order` no se toca: cada comanda llega
al cierre genuinamente cubierta, no por excepción.

La pertenencia vive en `orders.table_bill_id`, una columna escalar: una comanda apunta a una
cuenta y a ninguna más, por construcción. Lo que hay que impedir además es que una segunda
cuenta RECLAME una comanda que ya está en una cuenta abierta —dos cajeros con la misma mesa en
pantalla es una situación corriente—, y eso no lo puede dar un índice: se hace con un UPDATE
condicional (`WHERE table_bill_id IS NULL`) comprobando cuántas filas cambiaron. Es atómico en
la base, que es lo que importa; la comprobación previa en la aplicación sólo sirve para dar un
error legible.

`receipt_prints` pasa a admitir una comanda O una cuenta, con CHECK de exclusividad. La
pregunta que responde esa tabla —"¿esto ya se imprimió, es reimpresión?"— es idéntica para las
dos, y dos tablas para una misma pregunta se desincronizan. Las filas existentes ya cumplen el
CHECK porque todas tienen `order_id`.

Revision ID: 0046_table_bills
Revises: 0045_qr_table_ordering
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_table_bills"
down_revision: str | None = "0045_qr_table_ordering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "table_bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("dining_table_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("total", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("opened_by_employee_id", sa.Uuid(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        # RESTRICT: una mesa con una cuenta abierta encima no se borra sin resolverla.
        sa.ForeignKeyConstraint(
            ["dining_table_id"], ["dining_tables.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_employee_id"], ["employees.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_table_bills_tenant_id", "table_bills", ["tenant_id"])
    op.create_index("ix_table_bills_branch_id", "table_bills", ["branch_id"])
    op.create_index(
        "ix_table_bills_dining_table_id", "table_bills", ["dining_table_id"]
    )
    op.create_index(
        "ix_table_bills_opened_by_employee_id", "table_bills", ["opened_by_employee_id"]
    )

    op.add_column("orders", sa.Column("table_bill_id", sa.Uuid(), nullable=True))
    op.create_index("ix_orders_table_bill_id", "orders", ["table_bill_id"])
    op.create_foreign_key(
        "fk_orders_table_bill_id_table_bills",
        "orders",
        "table_bills",
        ["table_bill_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "receipt_prints", sa.Column("table_bill_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        "ix_receipt_prints_table_bill_id", "receipt_prints", ["table_bill_id"]
    )
    op.create_foreign_key(
        "fk_receipt_prints_table_bill_id_table_bills",
        "receipt_prints",
        "table_bills",
        ["table_bill_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "receipt_prints", "order_id", existing_type=sa.Uuid(), nullable=True
    )
    op.create_check_constraint(
        "ck_receipt_prints_order_xor_bill",
        "receipt_prints",
        "(order_id IS NULL) <> (table_bill_id IS NULL)",
    )


def downgrade() -> None:
    # Las impresiones de cuenta se van primero: sin ellas, `order_id` puede volver a NOT NULL.
    op.execute("DELETE FROM receipt_prints WHERE table_bill_id IS NOT NULL")
    op.drop_constraint(
        "ck_receipt_prints_order_xor_bill", "receipt_prints", type_="check"
    )
    op.alter_column(
        "receipt_prints", "order_id", existing_type=sa.Uuid(), nullable=False
    )
    op.drop_constraint(
        "fk_receipt_prints_table_bill_id_table_bills",
        "receipt_prints",
        type_="foreignkey",
    )
    op.drop_index("ix_receipt_prints_table_bill_id", table_name="receipt_prints")
    op.drop_column("receipt_prints", "table_bill_id")

    op.drop_constraint("fk_orders_table_bill_id_table_bills", "orders", type_="foreignkey")
    op.drop_index("ix_orders_table_bill_id", table_name="orders")
    op.drop_column("orders", "table_bill_id")

    op.drop_index("ix_table_bills_opened_by_employee_id", table_name="table_bills")
    op.drop_index("ix_table_bills_dining_table_id", table_name="table_bills")
    op.drop_index("ix_table_bills_branch_id", table_name="table_bills")
    op.drop_index("ix_table_bills_tenant_id", table_name="table_bills")
    op.drop_table("table_bills")
