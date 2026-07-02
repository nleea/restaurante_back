"""kitchen station roles and order kitchen_state ready rollup

Revision ID: 0004_kitchen_roles_rollup
Revises: 0003_rbac
Create Date: 2026-06-30 00:00:00.000000

Additive, backward-compatible columns:
- ``product_stations.role`` (nullable, <=60 chars): what a station does for a product.
- ``order_item_stations.role`` (nullable, <=60 chars): the role captured onto a ticket at
  routing time (frozen at fire time).
- ``orders.kitchen_state`` (``none | in_kitchen | ready``, default ``none``): the order's
  derived kitchen readiness, persisted for O(1) reads by Salón/Dispatch.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_kitchen_roles_rollup"
down_revision: str | None = "0003_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_stations",
        sa.Column("role", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "order_item_stations",
        sa.Column("role", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "kitchen_state",
            sa.String(length=20),
            server_default="none",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "kitchen_state")
    op.drop_column("order_item_stations", "role")
    op.drop_column("product_stations", "role")
