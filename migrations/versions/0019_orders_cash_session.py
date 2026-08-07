"""orders.cash_session_id — the operating shift an order belongs to

Revision ID: 0019_orders_cash_session
Revises: 0018_guest_profile
Create Date: 2026-07-21 00:00:00.000000

Adds a nullable `orders.cash_session_id` (FK → cash_sessions, SET NULL) stamped at
order creation with the branch's open cash session. It anchors the order — and, via
the order, its deliveries and kitchen tickets — to an operating shift, so live boards
show only the open session's work and closed sessions become per-shift history.
Existing rows backfill to NULL and are treated as belonging to no live shift.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_orders_cash_session"
down_revision: str | None = "0018_guest_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("cash_session_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_cash_session_id_cash_sessions",
        "orders",
        "cash_sessions",
        ["cash_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_orders_cash_session_id"), "orders", ["cash_session_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_cash_session_id"), table_name="orders")
    op.drop_constraint(
        "fk_orders_cash_session_id_cash_sessions", "orders", type_="foreignkey"
    )
    op.drop_column("orders", "cash_session_id")
