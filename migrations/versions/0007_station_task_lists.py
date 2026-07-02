"""itemized task lists on product-station mappings and tickets

Revision ID: 0007_station_task_lists
Revises: 0006_ticket_station_unique
Create Date: 2026-07-01 00:00:00.000000

Additive: ``tasks`` (JSON string array, default ``[]``) on ``product_stations`` (config:
what the station owes the product, e.g. "Carne de hamburguesa", "Tocineta ahumada") and on
``order_item_stations`` (frozen copy at routing time, like ``role``). Read-only detail for
the KDS — ticket granularity and constraints are unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_station_task_lists"
down_revision: str | None = "0006_ticket_station_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_stations",
        sa.Column("tasks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "order_item_stations",
        sa.Column("tasks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("order_item_stations", "tasks")
    op.drop_column("product_stations", "tasks")
