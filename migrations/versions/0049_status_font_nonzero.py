"""Fuentes de los estados de texto a las dos que el proveedor publica de verdad

Revision ID: 0049_status_font_nonzero
Revises: 0048_whatsapp_options_menu
Create Date: 2026-09-23 00:00:00.000000

El editor ofrecía cinco fuentes numeradas de 0 a 4 (Normal, Serif, Redondeada, Estrecha,
Manuscrita), y casi ninguna salía:

- Evolution valida con `if (!status.font)`, así que `font = 0` (la "Normal", la del borrador por
  defecto) cuenta como "sin fuente" y el estado de texto se cae con 400 al publicar.
- El número va tal cual a `ExtendedTextMessage.FontType` de Baileys: `SYSTEM=0, SYSTEM_TEXT=1,
  FB_SCRIPT=2, SYSTEM_BOLD=6…`. No hay 3 ni 4, y el 1 y el 2 no eran "Serif" ni "Redondeada".

Ahora quedan dos: `1` (Normal, `SYSTEM_TEXT`) y `2` (Manuscrita, `FB_SCRIPT`). La conversión
mapea por INTENCIÓN, no por número: lo que se eligió como Manuscrita (4) pasa a 2; todo lo demás
(0 a 3) a Normal, que es lo más cercano a lo que el dueño vio en la previa.

Es una migración de datos: no cambia el esquema. `downgrade` es con pérdida —Serif, Redondeada y
Estrecha ya no se distinguen de Normal— y devuelve 1→0 y 2→4.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049_status_font_nonzero"
down_revision: str | None = "0048_whatsapp_options_menu"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE whatsapp_statuses SET font = CASE WHEN font = 4 THEN 2 ELSE 1 END "
        "WHERE type = 'text' AND font BETWEEN 0 AND 4"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE whatsapp_statuses SET font = CASE WHEN font = 2 THEN 4 ELSE 0 END "
        "WHERE type = 'text' AND font IN (1, 2)"
    )
