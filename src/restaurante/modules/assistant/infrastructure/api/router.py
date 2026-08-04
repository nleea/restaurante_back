"""API del asistente: preguntar, ver lo gastado y decidir cuánto se compra.

Cuatro endpoints y una asimetría deliberada en los permisos: preguntar es `assistant.use`,
pero ver el consumo y encender el asistente es `assistant.manage`. Son dos personas: quien
pregunta cuánto se vendió ayer no es necesariamente quien decide cuánto saldo se compra.

Preguntar desde aquí **no salta ninguna comprobación**: pasa por el mismo punto de
estrangulamiento que WhatsApp, con las herramientas filtradas por los permisos EFECTIVOS de
quien pregunta en esta misma petición.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from restaurante.modules.assistant.application.use_cases.entitlements import (
    save_entitlement as save_entitlement_use_case,
)
from restaurante.modules.assistant.domain.plans import PLANS
from restaurante.modules.assistant.infrastructure.api.deps import (
    ConversationDep,
    MeteredDep,
    RepositoryDep,
    SessionDep,
    TenantDep,
    employee_tools,
)
from restaurante.modules.assistant.infrastructure.api.schemas import (
    AskRequest,
    AskResponse,
    PlanResponse,
    SaveEntitlementRequest,
    UsageEntryResponse,
    UsageResponse,
)
from restaurante.modules.identity.infrastructure.api.deps import (
    AuthorizationDep,
    CurrentUserDep,
    require_permission,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])

_USE = Depends(require_permission("assistant.use"))
_MANAGE = Depends(require_permission("assistant.manage"))


@router.post("/ask", response_model=AskResponse, dependencies=[_USE])
async def ask(
    payload: AskRequest,
    tenant_id: TenantDep,
    session: SessionDep,
    service: ConversationDep,
    current_user: CurrentUserDep,
    authz: AuthorizationDep,
) -> AskResponse:
    """Una pregunta desde el panel, contestada dentro de los permisos de quien la hace.

    Los permisos se resuelven AQUÍ, en esta petición, y no se toman de la sesión: quitarle
    un permiso a alguien tiene efecto en su siguiente pregunta.
    """
    codes = await authz.effective_codes(tenant_id, current_user.id)
    tools = await employee_tools(session, tenant_id, payload.branch_id, set(codes))
    answer = await service.ask_as_employee(
        tenant_id, payload.branch_id, current_user.id, payload.question, tools
    )
    return AskResponse.of(answer)


@router.get("/usage", response_model=UsageResponse, dependencies=[_MANAGE])
async def usage(tenant_id: TenantDep, metered: MeteredDep) -> UsageResponse:
    """El saldo del periodo, proyectado sobre el libro mayor."""
    return UsageResponse.of(await metered.usage_status(tenant_id))


@router.get(
    "/usage/recent",
    response_model=list[UsageEntryResponse],
    dependencies=[_MANAGE],
)
async def recent_usage(
    tenant_id: TenantDep,
    repo: RepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[UsageEntryResponse]:
    """Las últimas llamadas, una por fila. Es lo que contesta "¿por qué me cobraste esto?"."""
    return [
        UsageEntryResponse(
            occurred_at=entry.occurred_at,
            caller_kind=entry.caller_kind,
            model=entry.model,
            tokens_in=entry.tokens_in,
            tokens_out=entry.tokens_out,
            billed_units=entry.billed_units,
            provider_cost=entry.provider_cost,
        )
        for entry in await repo.recent_usage(tenant_id, limit)
    ]


@router.get("/plans", response_model=list[PlanResponse], dependencies=[_MANAGE])
async def plans() -> list[PlanResponse]:
    """Los planes que existen. Sin lo que nos cuestan a nosotros."""
    return [
        PlanResponse(
            name=plan.name,
            max_input_tokens=plan.max_input_tokens,
            max_output_tokens=plan.max_output_tokens,
        )
        for plan in PLANS.values()
    ]


@router.put("/entitlement", response_model=UsageResponse, dependencies=[_MANAGE])
async def save_entitlement(
    payload: SaveEntitlementRequest,
    tenant_id: TenantDep,
    repo: RepositoryDep,
    metered: MeteredDep,
) -> UsageResponse:
    """Qué plan tiene este negocio y cuánto compró.

    Encenderlo sin unidades se rechaza en el dominio: un asistente encendido con cuota cero
    contesta con el mensaje de agotado desde el primer mensaje, que parece una avería.
    """
    await save_entitlement_use_case(repo, payload.to_entity(tenant_id))
    return UsageResponse.of(await metered.usage_status(tenant_id))
