"""cash station: movement category + close observations

Revision ID: 2ed5e401d539
Revises: 0011_shift_scheduling
Create Date: 2026-07-11 12:07:49.685440

Cash movements gain a `category` (entry/withdrawal/expense/sale/other) so the
station can classify the ledger; existing rows backfill to 'other' via the
server default. Cash sessions gain close-time observations: free-text `notes`,
an `incident` flag and an `incident_note`.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ed5e401d539"
down_revision: str | None = "0011_shift_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cash_movements",
        sa.Column(
            "category", sa.String(length=20), server_default="other", nullable=False
        ),
    )
    op.add_column(
        "cash_sessions", sa.Column("notes", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "cash_sessions",
        sa.Column(
            "incident", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "cash_sessions",
        sa.Column("incident_note", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cash_sessions", "incident_note")
    op.drop_column("cash_sessions", "incident")
    op.drop_column("cash_sessions", "notes")
    op.drop_column("cash_movements", "category")
