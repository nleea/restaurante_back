"""operating_hours — structured per-branch opening windows

Revision ID: 0020_operating_hours
Revises: 0019_orders_cash_session
Create Date: 2026-07-21 00:00:00.000000

Adds the branch-scoped `operating_hours` table: one row per open window (weekday +
open/close minutes-from-midnight). Multiple rows per (branch, weekday) express split
windows; a weekday with no row is closed; `close_minute <= open_minute` crosses midnight.
Drives the storefront "abrimos a las X" copy — informational, not an order gate.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_operating_hours"
down_revision: str | None = "0019_orders_cash_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operating_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_minute", sa.Integer(), nullable=False),
        sa.Column("close_minute", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_operating_hours_tenant_id"), "operating_hours", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_operating_hours_branch_id"), "operating_hours", ["branch_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_operating_hours_branch_id"), table_name="operating_hours")
    op.drop_index(op.f("ix_operating_hours_tenant_id"), table_name="operating_hours")
    op.drop_table("operating_hours")
