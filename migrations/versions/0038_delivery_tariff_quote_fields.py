"""Add branch delivery tariff bands and auditable quote fields.

Revision ID: 0038_delivery_tariff_quote_fields
Revises: 0037_order_delivery_fee
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_delivery_tariff_quote"
down_revision: str | None = "0037_order_delivery_fee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_tariff_bands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("max_distance_km", sa.Numeric(6, 6), nullable=False),
        sa.Column("fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "position", name="uq_delivery_tariff_band_position"),
        sa.UniqueConstraint("branch_id", "max_distance_km", name="uq_delivery_tariff_band_max"),
    )
    for name, type_ in (
        ("quote_raw_distance_km", sa.Numeric(6, 3)), ("quote_buffer_km", sa.Numeric(4, 3)),
        ("quote_distance_km", sa.Numeric(6, 3)), ("quoted_fee", sa.Numeric(12, 2)),
    ):
        op.add_column("order_deliveries", sa.Column(name, type_, nullable=True))
    op.add_column("order_deliveries", sa.Column("quote_status", sa.String(24), nullable=False, server_default="pending_quote"))
    op.add_column("order_deliveries", sa.Column("quote_method", sa.String(80), nullable=True))
    op.add_column("order_deliveries", sa.Column("quoted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("order_deliveries", sa.Column("quote_failure_reason", sa.String(255), nullable=True))


def downgrade() -> None:
    for name in ("quote_failure_reason", "quoted_at", "quote_method", "quote_status", "quoted_fee", "quote_distance_km", "quote_buffer_km", "quote_raw_distance_km"):
        op.drop_column("order_deliveries", name)
    op.drop_table("delivery_tariff_bands")
