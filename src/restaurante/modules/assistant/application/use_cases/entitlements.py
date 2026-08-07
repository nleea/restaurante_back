"""Guardar el derecho de un tenant, con la regla que la pantalla no puede sostener sola.

**Encender el asistente sin unidades se rechaza aquí, en el dominio.** No es una preferencia
del dueño: un asistente encendido con cuota cero contesta el mensaje de agotado desde el
primer "hola", y eso no se lee como "se acabó el saldo" sino como "esto está roto". Es la
misma forma que el colchón de recuperación cero en alertas — el fallo que la validación
existe para impedir, rechazado donde no se puede saltar.
"""

from __future__ import annotations

from restaurante.modules.assistant.domain.entities import AssistantEntitlement
from restaurante.modules.assistant.domain.plans import PLANS
from restaurante.modules.assistant.domain.ports import AssistantRepository
from restaurante.shared.domain.errors import ValidationError


async def save_entitlement(
    repo: AssistantRepository, entitlement: AssistantEntitlement
) -> AssistantEntitlement:
    if entitlement.plan not in PLANS:
        raise ValidationError(
            f"El plan '{entitlement.plan}' no existe. Disponibles: "
            + ", ".join(sorted(PLANS))
        )
    if entitlement.is_enabled and entitlement.monthly_quota_units <= 0:
        raise ValidationError(
            "No se puede encender el asistente sin unidades: contestaría que se agotó el "
            "saldo desde el primer mensaje."
        )
    return await repo.save_entitlement(entitlement)
