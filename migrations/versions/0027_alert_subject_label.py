"""alerts.subject_label — cómo se llama aquello de lo que habla la alerta

Revision ID: 0027_alert_subject_label
Revises: 0026_employee_whatsapp_contact
Create Date: 2026-07-30 00:00:00.000000

La alerta guardaba `subject_ref` —el id del insumo— y el nombre se volvía a deducir en cada
pasada, preguntándole al evaluador. Eso funciona mientras la condición siga disparando, y deja
de funcionar exactamente en el hueco de la histéresis: el azúcar sube por encima del mínimo
pero sin pasar el colchón, así que la alerta sigue abierta y ya no "dispara" — nadie recoge su
nombre, y el aviso escalado sale diciendo `5d46e088-ee6a-4b88-…` en vez de "Azúcar".

Se guarda el nombre porque **la alerta ES sobre el Azúcar**, y saberlo no debería depender de
volver a preguntárselo a otro módulo. El `detail` ("quedan 1.84 de 3") NO se guarda a
propósito: es una medición, y media hora después sería un número viejo presentado como actual.

Nullable: las alertas que ya existen no tienen nombre guardado y caen en la referencia, igual
que antes. Nada que rellenar hacia atrás.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_alert_subject_label"
down_revision: str | None = "0026_employee_whatsapp_contact"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alerts", sa.Column("subject_label", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alerts", "subject_label")
