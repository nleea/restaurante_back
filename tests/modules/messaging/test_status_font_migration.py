"""La migración 0049 mapea las fuentes por INTENCIÓN, no por número.

Se corre el `upgrade`/`downgrade` de verdad contra una tabla mínima en SQLite: el SQL es un
`CASE` portable, y lo que importa probar es el mapeo (Manuscrita 4→2, el resto →1), que es lo que
cambió la visual de los estados ya programados.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "0049_status_font_nonzero.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0049", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(step: str, rows: list[tuple[str, int | None]]) -> list[tuple[str, Any]]:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE whatsapp_statuses (id INTEGER PRIMARY KEY, type TEXT, font INTEGER)"
            )
        )
        for i, (status_type, font) in enumerate(rows):
            conn.execute(
                sa.text("INSERT INTO whatsapp_statuses VALUES (:id, :type, :font)"),
                {"id": i, "type": status_type, "font": font},
            )
        module = _migration()
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, step)()
        result = conn.execute(
            sa.text("SELECT type, font FROM whatsapp_statuses ORDER BY id")
        )
        return [tuple(r) for r in result]


def test_upgrade_keeps_handwriting_and_folds_the_rest_into_normal() -> None:
    rows = [("text", 0), ("text", 1), ("text", 2), ("text", 3), ("text", 4)]

    assert _run("upgrade", rows) == [
        ("text", 1),
        ("text", 1),
        ("text", 1),
        ("text", 1),
        ("text", 2),
    ]


def test_upgrade_leaves_image_statuses_alone() -> None:
    assert _run("upgrade", [("image", None), ("image", 0)]) == [
        ("image", None),
        ("image", 0),
    ]


def test_downgrade_maps_back_to_the_old_numbering() -> None:
    rows = [("text", 1), ("text", 2), ("image", None)]

    assert _run("downgrade", rows) == [("text", 0), ("text", 4), ("image", None)]
