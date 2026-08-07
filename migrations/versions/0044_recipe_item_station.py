"""Let a recipe line say where that ingredient is worked in that dish.

`ingredients.default_station_id` answers "where is beef worked?" — a question with one global
answer. It cannot answer "where is the rice worked?", because rice is boiled in one plate and
fried in another, and fish is grilled in one and battered in another.

The recipe line IS the (dish, ingredient) pair, so it is the only place that question has an
answer. This is an override, not a replacement: the default still covers every ingredient that
does not need it, and derivation reads `COALESCE(line.station_id, ingredient.default_station_id)`.

`ON DELETE SET NULL`: reorganising the kitchen must not block or delete recipes; falling back to
the ingredient's default is the correct degradation.

Nullable with no backfill — every existing line keeps using its ingredient's default.

Revision ID: 0044_recipe_item_station
Revises: 0043_ingredient_default_station
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_recipe_item_station"
down_revision: str | None = "0043_ingredient_default_station"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recipe_items", sa.Column("station_id", sa.Uuid(), nullable=True))
    op.create_index("ix_recipe_items_station_id", "recipe_items", ["station_id"])
    op.create_foreign_key(
        "fk_recipe_items_station_id_kitchen_stations",
        "recipe_items",
        "kitchen_stations",
        ["station_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_recipe_items_station_id_kitchen_stations",
        "recipe_items",
        type_="foreignkey",
    )
    op.drop_index("ix_recipe_items_station_id", table_name="recipe_items")
    op.drop_column("recipe_items", "station_id")
