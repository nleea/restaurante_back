"""unique constraint on order_item_stations (order_item_id, kitchen_station_id)

Revision ID: 0006_ticket_station_unique
Revises: 0005_recipe_details
Create Date: 2026-07-01 00:00:00.000000

Routing idempotency was an app-level check-then-insert; under concurrency it could
duplicate a ticket. Dedupe first (keep the most advanced ticket per pair, oldest on
ties), then let the database enforce the invariant.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_ticket_station_unique"
down_revision: str | None = "0005_recipe_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep the "best" ticket per (order_item, station): highest status rank, then oldest
# entered_at, then smallest id as a final deterministic tie-break.
_DEDUPE_SQL = """
DELETE FROM order_item_stations AS a
USING order_item_stations AS b
WHERE a.order_item_id = b.order_item_id
  AND a.kitchen_station_id = b.kitchen_station_id
  AND a.id <> b.id
  AND (
    (CASE b.status WHEN 'ready' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
      > (CASE a.status WHEN 'ready' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
    OR (
      (CASE b.status WHEN 'ready' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
        = (CASE a.status WHEN 'ready' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
      AND (b.entered_at < a.entered_at
           OR (b.entered_at = a.entered_at AND b.id < a.id))
    )
  )
"""


def upgrade() -> None:
    op.execute(_DEDUPE_SQL)
    op.create_unique_constraint(
        "uq_order_item_stations_item_station",
        "order_item_stations",
        ["order_item_id", "kitchen_station_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_order_item_stations_item_station",
        "order_item_stations",
        type_="unique",
    )
