"""Give an insumo the kitchen station where it is worked.

The station a dish needs and the ingredients it is made of were two facts that never met: the
recipes module did not mention stations at all, so the KDS task list on `product_stations.tasks`
was typed by hand and drifted silently from the recipe behind it.

The insumo is the datum both sides share. With a station on it, a product's whole assignment —
which stations and what each one owes — becomes derivable from its recipe.

`ON DELETE SET NULL` on purpose: deleting a station is kitchen configuration and must not be
held hostage by insumos, and losing a suggestion costs one click to restore.

Nullable with no backfill: every existing insumo starts without a station and the suggestion
comes back empty until somebody assigns them. Nothing reads the column yet, so there is no
incompatible window between this migration and the code that follows.

Revision ID: 0043_ingredient_default_station
Revises: 0042_release_orphan_deliveries
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_ingredient_default_station"
down_revision: str | None = "0042_release_orphan_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingredients",
        sa.Column("default_station_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_ingredients_default_station_id",
        "ingredients",
        ["default_station_id"],
    )
    op.create_foreign_key(
        "fk_ingredients_default_station_id_kitchen_stations",
        "ingredients",
        "kitchen_stations",
        ["default_station_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ingredients_default_station_id_kitchen_stations",
        "ingredients",
        type_="foreignkey",
    )
    op.drop_index("ix_ingredients_default_station_id", table_name="ingredients")
    op.drop_column("ingredients", "default_station_id")
