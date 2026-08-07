"""Give every dining table a printable code, and every order its diner and its origin.

A QR stuck to a table has to carry three things the public menu already knows how to receive —
tenant, branch — plus one it does not: the table. `dining_tables.code` is that one. It is added
nullable, backfilled for every table that already exists, and only then made NOT NULL with its
per-branch unique index, all inside this one `upgrade`: a table without a code cannot be reached
by any QR, so there is no honest intermediate state to leave the database in.

The code is generated here with the same alphabet the application uses, but inlined rather than
imported: a migration is a frozen snapshot of a schema change, and importing application code
would let a future refactor rewrite what this historical migration does.

`orders.diner_name` and `orders.origin` come along because they are the same story from the
order's side. `origin` defaults to `staff` at the server: everything that existed before a
customer could order for themselves was, by definition, taken by staff.

Revision ID: 0045_qr_table_ordering
Revises: 0044_recipe_item_station
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_qr_table_ordering"
down_revision: str | None = "0044_recipe_item_station"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sin 0/O ni 1/I/L: quien no pueda escanear va a teclear lo que lee.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_LENGTH = 6


def _mint(taken: set[str]) -> str:
    """Un código libre dentro de su sede. `taken` es por sede, no global."""
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
        if code not in taken:
            taken.add(code)
            return code


def upgrade() -> None:
    op.add_column("dining_tables", sa.Column("code", sa.String(length=12), nullable=True))

    # Backfill. Se agrupa por sede porque la unicidad es por sede: dos sucursales pueden
    # repetir un código sin que ningún QR se vuelva ambiguo, ya que la sede va en la ruta.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, branch_id FROM dining_tables ORDER BY branch_id, id")
    ).fetchall()
    per_branch: dict[str, set[str]] = {}
    for table_id, branch_id in rows:
        taken = per_branch.setdefault(str(branch_id), set())
        bind.execute(
            sa.text("UPDATE dining_tables SET code = :code WHERE id = :id"),
            {"code": _mint(taken), "id": table_id},
        )

    op.alter_column("dining_tables", "code", existing_type=sa.String(length=12), nullable=False)
    op.create_unique_constraint(
        "uq_dining_tables_branch_code", "dining_tables", ["branch_id", "code"]
    )

    op.add_column("orders", sa.Column("diner_name", sa.String(length=60), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "origin",
            sa.String(length=16),
            nullable=False,
            server_default="staff",
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "origin")
    op.drop_column("orders", "diner_name")
    op.drop_constraint("uq_dining_tables_branch_code", "dining_tables", type_="unique")
    op.drop_column("dining_tables", "code")
