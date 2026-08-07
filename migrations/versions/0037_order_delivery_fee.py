"""Persist the frozen delivery charge on orders.

Revision ID: 0037_order_delivery_fee
Revises: 0036_alert_reminders
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_order_delivery_fee"
down_revision: str | None = "0036_alert_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "delivery_fee",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_fee")
