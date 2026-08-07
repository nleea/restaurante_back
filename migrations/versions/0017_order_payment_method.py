"""orders.payment_method intent column

Revision ID: 0017_order_payment_method
Revises: 0016_menu_appearance
Create Date: 2026-07-18 00:00:00.000000

Adds a nullable `orders.payment_method` (String(30)) that records the customer's
CHOSEN payment method as an intent — e.g. a public storefront web order where the
customer picks "efectivo"/"transferencia" but has not paid yet. It is deliberately
NOT an `order_payments` row: that models money actually received (it requires a cash
session and an amount and has no pending state), so staff register a real payment when
they collect. Existing rows backfill to NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_order_payment_method"
down_revision: str | None = "0016_menu_appearance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("payment_method", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_method")
