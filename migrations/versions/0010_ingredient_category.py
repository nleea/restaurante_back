"""ingredients: optional free-text category

Revision ID: 0010_ingredient_category
Revises: 0009_delivery_ts_notes
Create Date: 2026-07-03 00:00:00.000000

The inventory board groups and filters insumos by category ("Carnes", "Lácteos", …).
Free text (≤50), nullable — no catalog table until pilots need renames/merges.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_ingredient_category"
down_revision: str | None = "0009_delivery_ts_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingredients", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("ingredients", "category")
