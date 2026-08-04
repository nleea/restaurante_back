"""Recordatorios de alertas: insistir hasta que alguien haga algo

Revision ID: 0036_alert_reminders
Revises: 0035_low_stock_buffer_percent
Create Date: 2026-08-01 00:00:00.000000

Cuatro cambios, y el que importa es el primero.

1. `alert_rules.remind_every_minutes` — cada cuánto insiste el panel. **Nace en 5, no en 0**, y
   eso le cambia el comportamiento a todo el mundo al desplegar. Se hace a ojos abiertos porque
   el comportamiento actual ES el defecto que este change arregla: el módulo avisaba una vez y
   callaba para siempre, así que una alerta que salta cuando nadie mira la pantalla se pierde.
   Nacer en 0 sería desplegar el arreglo y que quien lo pidió siga sin recordatorios hasta que
   descubra por su cuenta un campo nuevo en una pantalla de ajustes.

2. `alerts.escalated_at` → `alerts.last_escalated_at`. Mismo dato, otro significado: antes era
   "ya escaló" (una vez y punto), ahora es "cuándo fue la última", porque el escalado se repite
   cada 4 horas. Se renombra en vez de añadir una columna para que no queden dos verdades.

3. `alerts.last_notified_at` — la última vez que el panel avisó. Las alertas abiertas la reciben
   en `NULL`, y eso las hace **debidas en el primer barrido**: son precisamente las que llevan
   horas calladas, así que recibir un recordatorio inmediato es lo correcto, no un efecto
   secundario.

4. `alerts.reminders_muted_at` — la tercera salida ("ya lo sé, cállate"). Nullable y vacía: nadie
   tiene nada silenciado todavía.

`alert_rules.escalation_after_minutes` baja su `server_default` de 30 a 5: el primer WhatsApp sale
a los 5 minutos. Los valores ya guardados **no** se tocan — a diferencia del colchón de la 0035,
aquí "30 minutos" siempre significó minutos y pudo elegirse con intención.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036_alert_reminders"
down_revision: str | None = "0035_low_stock_buffer_percent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column(
            "remind_every_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    op.alter_column(
        "alert_rules",
        "escalation_after_minutes",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("5"),
    )
    op.alter_column("alerts", "escalated_at", new_column_name="last_escalated_at")
    op.add_column(
        "alerts",
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("reminders_muted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alerts", "reminders_muted_at")
    op.drop_column("alerts", "last_notified_at")
    op.alter_column("alerts", "last_escalated_at", new_column_name="escalated_at")
    op.alter_column(
        "alert_rules",
        "escalation_after_minutes",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("30"),
    )
    op.drop_column("alert_rules", "remind_every_minutes")
