"""API de alertas: qué está encendido, tomarlo, y cómo se configuran las reglas.

Cuatro endpoints y ninguno dispara nada. Disparar es cosa del worker: una alerta que
apareciera porque alguien abrió una pantalla sería una alerta que no existe cuando nadie
mira, que es justo al revés de para lo que sirve el módulo.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from restaurante.modules.alerts.domain.entities import KNOWN_RULE_KEYS, AlertRule
from restaurante.modules.alerts.infrastructure.api.deps import (
    LifecycleDep,
    RepositoryDep,
    SessionDep,
    TenantDep,
)
from restaurante.modules.alerts.infrastructure.api.schemas import (
    AlertResponse,
    AlertRuleResponse,
    ContactableChatResponse,
    EscalationReachResponse,
    EscalationRecipientResponse,
    LinkChatRequest,
    SaveAlertRuleRequest,
)
from restaurante.modules.alerts.infrastructure.channels import ALERTS_TOPIC
from restaurante.modules.alerts.infrastructure.whatsapp_escalation import (
    WhatsAppEscalationChannel,
)
from restaurante.modules.identity.infrastructure.api.deps import (
    CurrentUserDep,
    require_permission,
)
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.staff.application.use_cases.manage_staff import StaffService
from restaurante.modules.staff.infrastructure.repositories import (
    SqlAlchemyStaffRepository,
)
from restaurante.shared.domain.errors import NotFoundError, ValidationError
from restaurante.shared.realtime.deps import EventStreamDep, event_stream_response

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Ver y tomar es el turno; configurar umbrales y a quién se le escribe a las 11 es el dueño.
_READ = Depends(require_permission("alerts.read"))
_MANAGE = Depends(require_permission("alerts.manage"))

BranchQuery = Annotated[uuid.UUID, Query(description="Sucursal activa.")]


@router.get("", response_model=list[AlertResponse], dependencies=[_READ])
async def list_open_alerts(
    branch_id: BranchQuery, repo: RepositoryDep, tenant_id: TenantDep
) -> list[AlertResponse]:
    """Lo que está encendido en esta sucursal. Vacío es la buena noticia."""
    alerts = await repo.list_open(tenant_id, branch_id)
    # Los nombres se resuelven de una pasada y cacheados: una sucursal con diez alertas
    # tomadas por la misma persona no puede hacer diez consultas iguales.
    names: dict[uuid.UUID, str | None] = {}
    out: list[AlertResponse] = []
    for alert in alerts:
        holder = None
        if alert.acknowledged_by is not None:
            if alert.acknowledged_by not in names:
                names[alert.acknowledged_by] = await repo.employee_name(
                    tenant_id, alert.acknowledged_by
                )
            holder = names[alert.acknowledged_by]
        out.append(AlertResponse.of(alert, holder))
    return out


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse, dependencies=[_READ])
async def acknowledge_alert(
    alert_id: uuid.UUID,
    branch_id: BranchQuery,
    lifecycle: LifecycleDep,
    repo: RepositoryDep,
    tenant_id: TenantDep,
    current_user: CurrentUserDep,
) -> AlertResponse:
    """Tomarla. Es `alerts.read` y no `manage`: quien está en el turno es quien la atiende.

    Perder la carrera devuelve un 409 que dice quién la tiene — no un error genérico, porque
    lo útil es que el segundo no repita el trabajo.
    """
    employee_id = await repo.employee_id_for_user(tenant_id, current_user.id, branch_id)
    if employee_id is None:
        raise ValidationError(
            "Tu usuario no está vinculado a un empleado activo de esta sucursal."
        )
    alert = await lifecycle.acknowledge(tenant_id, alert_id, employee_id)
    return AlertResponse.of(
        alert, await repo.employee_name(tenant_id, employee_id)
    )


@router.post("/{alert_id}/mute", response_model=AlertResponse, dependencies=[_READ])
async def mute_alert_reminders(
    alert_id: uuid.UUID,
    branch_id: BranchQuery,
    lifecycle: LifecycleDep,
    tenant_id: TenantDep,
) -> AlertResponse:
    """Callarla sin tomarla: "ya lo sé, el proveedor viene el viernes".

    `alerts.read` igual que tomarla — quien puede hacerse cargo puede decir que ya lo sabe.

    **No la toma ni la cierra**, y ésa es toda la gracia: sigue abierta, sin dueño y en el panel.
    Si callar exigiera tomarla, el registro de quién atiende qué se llenaría de mentiras en una
    semana y dejaría de servir para nada.

    Idempotente: silenciar dos veces devuelve la alerta, no un error. Quien vuelve a pulsar el
    botón merece ver el estado.
    """
    return AlertResponse.of(await lifecycle.mute_reminders(tenant_id, alert_id))


@router.get("/rules", response_model=list[AlertRuleResponse], dependencies=[_READ])
async def list_rules(
    branch_id: BranchQuery, repo: RepositoryDep, tenant_id: TenantDep
) -> list[AlertRuleResponse]:
    """Las reglas conocidas para esta sucursal, con su configuración vigente.

    Se materializan las que no tienen fila: una regla sin configurar existe y está apagada,
    y la pantalla tiene que poder encenderla sin que alguien la haya sembrado antes.
    """
    stored = {r.rule_key: r for r in await repo.list_rules(tenant_id, branch_id)}
    return [
        AlertRuleResponse.of(
            stored.get(key)
            or AlertRule(tenant_id=tenant_id, branch_id=branch_id, rule_key=key)
        )
        for key in KNOWN_RULE_KEYS
    ]


@router.get(
    "/escalation-reach", response_model=EscalationReachResponse, dependencies=[_READ]
)
async def escalation_reach(
    branch_id: BranchQuery, session: SessionDep, tenant_id: TenantDep
) -> EscalationReachResponse:
    """Cuántas personas recibirían un escalado por WhatsApp en esta sucursal.

    La pantalla de configuración lo enseña junto al interruptor porque, sin esto, encender
    "escalar por WhatsApp" y que no pase nada es indistinguible de que esté roto. Las causas
    son cuatro y ninguna es evidente: no hay número conectado, nadie está señalado para
    recibirlo, los señalados no tienen teléfono, o —la que nadie adivina— nadie ha escrito
    nunca al número del negocio, que es lo que el guardián exige para poder escribirle.
    """
    reach = await WhatsAppEscalationChannel(session).reach(tenant_id, branch_id)
    return EscalationReachResponse(
        has_session=reach.has_session,
        subscribed=reach.subscribed,
        with_chat=reach.with_chat,
        reachable=reach.reachable,
    )


@router.get(
    "/escalation-recipients",
    response_model=list[EscalationRecipientResponse],
    dependencies=[_READ],
)
async def escalation_recipients(
    branch_id: BranchQuery, session: SessionDep, tenant_id: TenantDep
) -> list[EscalationRecipientResponse]:
    """Quién está señalado para recibir alertas en esta sucursal, y a quién se le puede.

    La ficha del empleado lo usa para poder decir, junto al interruptor, si a ESA persona le
    llegaría — que es distinto de si el escalado está bien configurado en general.
    """
    roster = await WhatsAppEscalationChannel(session).roster(tenant_id, branch_id)
    return [
        EscalationRecipientResponse(
            employee_id=recipient.employee_id,
            name=recipient.name,
            has_chat=bool(recipient.address),
            reachable=reachable,
        )
        for recipient, reachable in roster
    ]


@router.get(
    "/contactable-chats",
    response_model=list[ContactableChatResponse],
    dependencies=[_MANAGE],
)
async def contactable_chats(
    branch_id: BranchQuery, session: SessionDep, tenant_id: TenantDep
) -> list[ContactableChatResponse]:
    """Los chats a los que se puede escribir en esta sucursal, del más reciente al más viejo.

    "Se puede escribir" = escribieron ellos primero, que es exactamente lo que exige el
    guardián. Por eso esta lista sirve para emparejar sin adivinar: cualquiera de estos es un
    destino válido, y nada fuera de ella lo es.
    """
    repo = SqlAlchemyMessagingRepository(session)
    return [
        ContactableChatResponse(contact_id=cid, name=name, address=address)
        for cid, name, address in await repo.list_contactable(tenant_id, branch_id)
    ]


@router.put(
    "/recipients/{employee_id}/chat",
    response_model=EscalationRecipientResponse,
    dependencies=[_MANAGE],
)
async def link_recipient_chat(
    employee_id: uuid.UUID,
    payload: LinkChatRequest,
    branch_id: BranchQuery,
    session: SessionDep,
    tenant_id: TenantDep,
) -> EscalationRecipientResponse:
    """Dice cuál de los chats es esta persona. `null` la desempareja.

    Vive en alertas y no en Personal porque es aquí donde el dato significa algo —a quién se
    le escribe cuando algo lleva rato ardiendo— y porque este módulo ya es el puente entre
    el personal y WhatsApp.
    """
    if payload.contact_id is not None:
        contact = await SqlAlchemyMessagingRepository(session).get_contact(
            tenant_id, payload.contact_id
        )
        if contact is None:
            raise NotFoundError("Ese chat no existe.")
    staff = StaffService(SqlAlchemyStaffRepository(session))
    await staff.set_whatsapp_contact(tenant_id, employee_id, payload.contact_id)

    roster = await WhatsAppEscalationChannel(session).roster(tenant_id, branch_id)
    for recipient, reachable in roster:
        if recipient.employee_id == employee_id:
            return EscalationRecipientResponse(
                employee_id=recipient.employee_id,
                name=recipient.name,
                has_chat=bool(recipient.address),
                reachable=reachable,
            )
    # Desemparejado, o no señalado: se responde con el estado real en vez de un 404.
    return EscalationRecipientResponse(
        employee_id=employee_id, name="—", has_chat=False, reachable=False
    )


@router.put("/rules/{rule_key}", response_model=AlertRuleResponse, dependencies=[_MANAGE])
async def save_rule(
    rule_key: str,
    payload: SaveAlertRuleRequest,
    branch_id: BranchQuery,
    lifecycle: LifecycleDep,
    tenant_id: TenantDep,
) -> AlertRuleResponse:
    if rule_key not in KNOWN_RULE_KEYS:
        raise NotFoundError(f"No existe la regla: {rule_key}")
    saved = await lifecycle.save_rule(payload.to_rule(tenant_id, branch_id, rule_key))
    return AlertRuleResponse.of(saved)


@router.get("/events", dependencies=[_READ])
async def stream_alert_events(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """El timbre de la sucursal (latido cada ~15 s).

    Los frames son pistas, no estado: al recibir uno el panel vuelve a pedir la lista. Con
    el broker caído degrada a latidos y el cliente se apoya en su cadencia de sondeo — que
    es lo correcto aquí: una alerta que aparece 30 segundos tarde sigue sirviendo, una
    pantalla que se queda congelada creyendo que todo está bien, no.
    """
    return event_stream_response(stream, ALERTS_TOPIC, tenant_id, branch_id)
