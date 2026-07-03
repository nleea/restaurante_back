"""order_deliveries: created_at/updated_at timestamps and notes

Revision ID: 0009_delivery_ts_notes
Revises: 0008_delivery_map
Create Date: 2026-07-03 00:00:00.000000

The dispatch board needs "recibido" times (elapsed labels, overdue heat) and per-delivery
notes. ``created_at``/``updated_at`` backfill existing rows with ``now()`` via the server
default — acceptable: the board only reads heat/elapsed on open (today's) deliveries.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_delivery_ts_notes"
down_revision: str | None = "0008_delivery_map"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_deliveries", sa.Column("notes", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "order_deliveries",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "order_deliveries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("order_deliveries", "updated_at")
    op.drop_column("order_deliveries", "created_at")
    op.drop_column("order_deliveries", "notes")
