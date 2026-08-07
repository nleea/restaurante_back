"""Por qué esa alerta sigue abierta. Sólo lee: no dispara, no resuelve, no toca nada.

    poetry run python -m scripts.diagnose_alerts

Existe porque "la alerta no se va" tiene cinco causas posibles y desde fuera son idénticas: la
regla con un colchón alto, el stock repuesto en OTRA sucursal, el worker muerto, la alerta ya
tomada, o el insumo sin mínimo. Adivinar cuál es cuesta más que mirarlo, y mirarlo a mano exige
cruzar tres tablas de dos módulos.

Para cada alerta abierta imprime el veredicto: si el evaluador la cerraría ahora mismo, y si no,
**por qué no**. Y al final dice si el barrido está vivo, que es la causa que no se ve en ninguna
tabla.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from restaurante.modules.alerts.domain.entities import RULE_LOW_STOCK
from restaurante.modules.alerts.infrastructure.models import AlertModel, AlertRuleModel
from restaurante.modules.alerts.infrastructure.readers import SqlAlchemyInventoryReader
from restaurante.shared.database import SessionFactory, engine
from restaurante.shared.tenancy.models import BranchModel, TenantModel

_LINE = "─" * 78

# El motor viene con `echo` encendido en desarrollo y aquí sólo estorba: quien lee esto busca el
# veredicto, no las consultas que lo produjeron.
# Se apaga en el MOTOR y no en el logger: con `echo`, SQLAlchemy decide por instancia y no
# consulta el nivel del logger, así que bajarlo no silencia nada. Quien lee esto busca el
# veredicto, no las consultas que lo produjeron.
engine.echo = False


async def main() -> None:
    async with SessionFactory() as session:
        tenants = {
            t.id: t.slug for t in (await session.execute(select(TenantModel))).scalars()
        }
        branches = {
            b.id: b.name for b in (await session.execute(select(BranchModel))).scalars()
        }

        open_alerts = list(
            (
                await session.execute(
                    select(AlertModel)
                    .where(AlertModel.status.in_(("fired", "acknowledged")))
                    .order_by(AlertModel.fired_at)
                )
            ).scalars()
        )
        print(_LINE)
        print(f"ALERTAS ABIERTAS: {len(open_alerts)}")
        print(_LINE)
        if not open_alerts:
            print("Ninguna. Si esperabas ver una, el problema es que no DISPARA, no que no cierre.")

        reader = SqlAlchemyInventoryReader(session)
        for alert in open_alerts:
            rule = (
                await session.execute(
                    select(AlertRuleModel).where(
                        AlertRuleModel.tenant_id == alert.tenant_id,
                        AlertRuleModel.branch_id == alert.branch_id,
                        AlertRuleModel.rule_key == alert.rule_key,
                    )
                )
            ).scalar_one_or_none()

            print()
            print(f"  {alert.subject_label or alert.subject_ref}  [{alert.rule_key}]")
            print(f"    tenant   : {tenants.get(alert.tenant_id, alert.tenant_id)}")
            print(f"    sucursal : {branches.get(alert.branch_id, alert.branch_id)}")
            print(f"    estado   : {alert.status}   disparada: {alert.fired_at}")
            if rule is None:
                print("    ⚠  NO HAY REGLA para esa (sucursal, clave): no se evalúa, no se cierra.")
                continue
            print(
                f"    regla    : encendida={rule.is_enabled} "
                f"colchón={rule.recovery_buffer} umbral={rule.threshold}"
            )
            if not rule.is_enabled:
                print("    ⚠  LA REGLA ESTÁ APAGADA. Una regla apagada no se evalúa, así que")
                print("       tampoco cierra lo que dejó abierto. Enciéndela o cierra a mano.")
                continue

            if alert.rule_key != RULE_LOW_STOCK:
                print("    (esta herramienta sólo sabe explicar el stock bajo)")
                continue

            levels = await reader.stock_for(
                alert.tenant_id, alert.branch_id, [alert.subject_ref]
            )
            if not levels:
                print("    ⚠  ESE INSUMO NO TIENE FILA DE STOCK EN ESTA SUCURSAL.")
                print("       El evaluador no puede verlo, así que nunca lo declara recuperado.")
                print("       Suele ser stock repuesto en OTRA sucursal.")
                continue
            level = levels[0]
            needed = level.minimum + rule.recovery_buffer
            print(
                f"    stock    : hay {level.current}  mínimo {level.minimum}  "
                f"colchón {rule.recovery_buffer}"
            )
            if level.current > needed:
                print(f"    ✓  DEBERÍA CERRARSE: {level.current} > {needed}.")
                print("       Si sigue abierta, el barrido NO se está ejecutando (ver abajo).")
            else:
                print(f"    ✗  NO cierra: hace falta pasar de {needed} y hay {level.current}.")
                if level.minimum <= 0:
                    print("       Además el mínimo es 0: este insumo no debería haber disparado.")

        print()
        print(_LINE)
        print("¿ESTÁ VIVO EL BARRIDO?")
        print(_LINE)
        print("Esta herramienta no puede verlo desde la base de datos. Compruébalo así:")
        print()
        print("  1) que el proceso exista:   pgrep -fl 'alerts.infrastructure.worker'")
        print("  2) que haya barrido hace poco, en el log del worker:")
        print("       'Barrido de alertas: N reglas, …'  ← sale una vez cada 5 minutos")
        print()
        print("  Si no aparece, arráncalo:   make alerts")
        print("  (necesita CACHE_BACKEND=redis y el REDIS_URL del entorno)")
        print()
        print(f"  Ahora son las {datetime.now(UTC):%H:%M:%S} UTC. El barrido corre en los")
        print("  minutos 0, 5, 10 … de cada hora: si en el próximo cambio de múltiplo de 5")
        print("  no sale esa línea en el log, el worker no está corriendo.")


if __name__ == "__main__":
    asyncio.run(main())
