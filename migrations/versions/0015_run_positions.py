"""delivery_run_positions: append-only live driver trail

Revision ID: 0015_run_positions
Revises: 0014_delivery_fail_reason
Create Date: 2026-07-17 00:00:00.000000

The dispatcher needs to see where each active driver is. This adds the append-only trail
table `delivery_run_positions` — one timestamped GPS fix per row, keyed by run, tenant- and
branch-scoped like every other delivery record. Additive, no backfill: it is inert until a
driver enables tracking, and rows are pruned when the run finishes.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_run_positions"
down_revision: str | None = "0014_delivery_fail_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_run_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_run_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["delivery_run_id"], ["delivery_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delivery_run_positions_tenant_id"),
        "delivery_run_positions",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_delivery_run_positions_branch_id"),
        "delivery_run_positions",
        ["branch_id"],
    )
    op.create_index(
        op.f("ix_delivery_run_positions_delivery_run_id"),
        "delivery_run_positions",
        ["delivery_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_delivery_run_positions_delivery_run_id"),
        table_name="delivery_run_positions",
    )
    op.drop_index(
        op.f("ix_delivery_run_positions_branch_id"),
        table_name="delivery_run_positions",
    )
    op.drop_index(
        op.f("ix_delivery_run_positions_tenant_id"),
        table_name="delivery_run_positions",
    )
    op.drop_table("delivery_run_positions")
