"""«Mi pedido»: leer y corregir el propio pedido desde el enlace, sin login.

Dos endpoints y un token. El token es una **URL-capacidad**: quien lo tiene edita ESE pedido y
ningún otro. No autentica a nadie, así que la respuesta no lleva nada que no sea de ese pedido.

Vencido, desconocido y de otro tenant responden lo mismo (404): distinguirlos convertiría esto
en un oráculo para averiguar qué pedidos existen.

Se monta ANTES que el router del storefront a propósito. `/storefront/{branch_code}/menu` tiene
la misma forma que `/storefront/orders/{token}`, y en FastAPI gana la que se declaró primero.
Los tokens son `token_urlsafe`, así que la colisión es teórica — pero depender de que ningún
token se llame nunca "menu" no es una garantía, es una apuesta.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from restaurante.modules.orders.infrastructure.payment_proof import MAX_PROOF_BYTES
from restaurante.modules.storefront.application.use_cases.edit_order import (
    AddLine,
    EditCommand,
    EditLine,
)
from restaurante.modules.storefront.infrastructure.api.deps import (
    OrderEditServiceDep,
    PaymentServiceDep,
    ProofStoreDep,
    TenantDep,
)
from restaurante.modules.storefront.infrastructure.api.schemas import (
    StorefrontOrderEditRequest,
    StorefrontOrderEditResponse,
    StorefrontOrderView,
    StorefrontPaymentProofResponse,
)
from restaurante.shared.domain.errors import ValidationError

router = APIRouter(prefix="/storefront/orders", tags=["storefront"])


@router.get("/{token}", response_model=StorefrontOrderView)
async def get_my_order(
    token: str, service: OrderEditServiceDep, tenant_id: TenantDep
) -> StorefrontOrderView:
    """El pedido del enlace: líneas, adiciones, notas, qué se deja cambiar, total y saldo."""
    return StorefrontOrderView.from_view(await service.view(tenant_id, token))


@router.patch("/{token}", response_model=StorefrontOrderEditResponse)
async def edit_my_order(
    token: str,
    payload: StorefrontOrderEditRequest,
    request: Request,
    service: OrderEditServiceDep,
    tenant_id: TenantDep,
) -> StorefrontOrderEditResponse:
    """Aplica la corrección y devuelve el pedido releído.

    Se devuelve la vista entera, no un acuse: un rechazo parcial no existe (o entra todo o no
    entra nada), pero el mundo pudo moverse mientras tanto, y la vista tiene que resincronizarse
    con lo que hay —no con lo que creía tener.
    """
    outcome = await service.apply(
        tenant_id,
        token,
        EditCommand(
            add=[
                AddLine(
                    variant_id=line.variant_id,
                    quantity=line.quantity,
                    addon_ids=list(line.addon_ids),
                    removed_ingredients=list(line.removed_ingredients),
                    note=line.note,
                )
                for line in payload.add
            ],
            edit=[
                EditLine(
                    item_id=change.item_id,
                    quantity=change.quantity,
                    add_addon_ids=list(change.add_addon_ids),
                    removed_ingredients=(
                        None
                        if change.removed_ingredients is None
                        else list(change.removed_ingredients)
                    ),
                    note=change.note,
                    variant_id=change.variant_id,
                )
                for change in payload.edit
            ],
        ),
        # Único rastro de quién usó el enlace: aquí no hay sesión que mirar.
        ip=request.client.host if request.client else None,
    )
    return StorefrontOrderEditResponse(
        total_before=f"{outcome.total_before:.2f}",
        order=StorefrontOrderView.from_view(await service.view(tenant_id, token)),
    )


# --- El comprobante del cliente ----------------------------------------------
@router.post("/{token}/payment-proof", response_model=StorefrontPaymentProofResponse)
async def upload_payment_proof(
    token: str,
    service: OrderEditServiceDep,
    payments: PaymentServiceDep,
    store_proof: ProofStoreDep,
    tenant_id: TenantDep,
    amount: Annotated[Decimal, Form()],
    file: Annotated[UploadFile, File()],
) -> StorefrontPaymentProofResponse:
    """Recibe el comprobante y lo deja **esperando a una persona**.

    Los bytes pasan por aquí y no por una URL prefirmada porque una firma no acota el tamaño de
    lo que se sube, y esta puerta es pública: cualquiera con un enlace vivo. Se comprueba tipo y
    tamaño ANTES de escribir nada.

    Lo que devuelve NO dice que el pedido esté pagado — dice que hay algo que mirar. El saldo
    sigue siendo el mismo hasta que alguien del restaurante lo verifica.
    """
    order, _items = await service.load(tenant_id, token)
    assert order.id is not None
    data = await file.read(MAX_PROOF_BYTES + 1)
    if len(data) > MAX_PROOF_BYTES:
        raise ValidationError("El comprobante pesa demasiado (máximo 5 MB).")
    proof_url = await store_proof(tenant_id, order.id, file.content_type or "", data)
    # El método sale del PEDIDO, no de lo que llegue en el formulario: el cliente ya eligió
    # cómo iba a pagar y dejarlo re-elegir aquí sólo crea un cobro que no cuadra con el
    # comprobante.
    claim = await payments.declare_payment(
        tenant_id, order.id, amount, order.payment_method or "transfer", proof_url
    )
    assert claim.id is not None
    return StorefrontPaymentProofResponse(
        claim_id=claim.id,
        status=claim.status,
        order=StorefrontOrderView.from_view(await service.view(tenant_id, token)),
    )
