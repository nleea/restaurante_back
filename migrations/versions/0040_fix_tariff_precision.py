"""Fix delivery_tariff_bands.max_distance_km precision.

Previously declared as NUMERIC(6, 6), which caps values below 1 (0.999999),
making the column unusable for real distances in km. Corrected to NUMERIC(6, 3),
consistent with order_deliveries.quote_raw_distance_km / quote_distance_km
(up to 999.999 km, 3 decimal places).

Revision ID: 0040_fix_tariff_precision
Revises: 0039_delivery_payment_requests
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_fix_tariff_precision"
down_revision: str | None = "0039_delivery_payment_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "delivery_tariff_bands",
        "max_distance_km",
        type_=sa.Numeric(6, 3),
        existing_type=sa.Numeric(6, 6),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "delivery_tariff_bands",
        "max_distance_km",
        type_=sa.Numeric(6, 6),
        existing_type=sa.Numeric(6, 3),
        existing_nullable=False,
    )