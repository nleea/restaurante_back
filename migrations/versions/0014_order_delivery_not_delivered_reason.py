"""delivery: not_delivered_reason on order_deliveries

Revision ID: 0014_order_delivery_not_delivered_reason
Revises: 0013_delivery_branch_scoping
Create Date: 2026-07-17 00:00:00.000000

Additive, nullable column recording WHY a delivery failed. Set only when a stop is marked
`not_delivered`; kept separate from `notes` (address/handling) so the failure reason stays
queryable and never clobbers address notes. No backfill — existing rows are simply null.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_delivery_fail_reason"
down_revision: str | None = "0013_delivery_branch_scoping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_deliveries",
        sa.Column("not_delivered_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_deliveries", "not_delivered_reason")
