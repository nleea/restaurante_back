"""employees.receives_alerts — a quién se le escribe cuando una alerta lleva rato sin tomar

Revision ID: 0025_employee_alert_subscription
Revises: 0024_alerts
Create Date: 2026-07-30 00:00:00.000000

Una elección explícita, no un permiso.

Antes, el escalado por WhatsApp iba a todo el que tuviera `alerts.read`, y eso mezclaba dos
cosas que no son la misma: **poder ver el panel de alertas** y **que le suene el móvil a las
once de la noche**. Con sólo el permiso, alguien que debía ver la pantalla pero no recibir
mensajes no tenía salida: para quitarle el mensaje había que quitarle la pantalla.

Nace en `false` para todos, igual que las reglas. Encender el escalado no le escribe a nadie
hasta que alguien señale a una persona — que es lo contrario de descubrir el módulo porque te
llegó un WhatsApp a medianoche que no pediste.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_employee_alert_subscription"
down_revision: str | None = "0024_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column(
            "receives_alerts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("employees", "receives_alerts")
