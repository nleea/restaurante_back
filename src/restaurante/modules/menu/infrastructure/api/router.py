"""Menu API: catalog management (categories, products, prices, variants, addons).

Reads require `menu.read`; writes require `menu.manage` (RBAC).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.menu.infrastructure.api.deps import MenuServiceDep, TenantDep
from restaurante.modules.menu.infrastructure.api.schemas import (
    AddonResponse,
    CategoryResponse,
    CreateAddonRequest,
    CreateCategoryRequest,
    CreateProductRequest,
    CreateProductVariantRequest,
    CreateVariantGroupRequest,
    CreateVariantOptionRequest,
    ProductPriceResponse,
    ProductResponse,
    ProductVariantResponse,
    SetPriceRequest,
    UpdateAddonRequest,
    UpdateCategoryRequest,
    UpdateProductRequest,
    UpdateProductVariantRequest,
    UpdateVariantGroupRequest,
    UpdateVariantOptionRequest,
    VariantGroupResponse,
    VariantOptionResponse,
)

router = APIRouter(prefix="/menu", tags=["menu"])

_READ = Depends(require_permission("menu.read"))
_WRITE = Depends(require_permission("menu.manage"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Categories -------------------------------------------------------------
@router.post("/categories", response_model=CategoryResponse, status_code=201, dependencies=[_WRITE])
async def create_category(
    payload: CreateCategoryRequest, service: MenuServiceDep, tenant_id: TenantDep
) -> CategoryResponse:
    cat = await service.create_category(
        tenant_id, payload.name, payload.parent_category_id, payload.position
    )
    return CategoryResponse.model_validate(cat, from_attributes=True)


@router.get("/categories", response_model=list[CategoryResponse], dependencies=[_READ])
async def list_categories(
    service: MenuServiceDep,
    tenant_id: TenantDep,
    active: bool | None = None,
    parent_id: uuid.UUID | None = None,
) -> list[CategoryResponse]:
    cats = await service.list_categories(tenant_id, active=active, parent_id=parent_id)
    return [CategoryResponse.model_validate(c, from_attributes=True) for c in cats]


@router.get("/categories/{category_id}", response_model=CategoryResponse, dependencies=[_READ])
async def get_category(
    category_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> CategoryResponse:
    cat = await service.get_category(tenant_id, category_id)
    return CategoryResponse.model_validate(cat, from_attributes=True)


@router.patch("/categories/{category_id}", response_model=CategoryResponse, dependencies=[_WRITE])
async def update_category(
    category_id: uuid.UUID,
    payload: UpdateCategoryRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> CategoryResponse:
    cat = await service.update_category(
        tenant_id, category_id, payload.model_dump(exclude_unset=True)
    )
    return CategoryResponse.model_validate(cat, from_attributes=True)


@router.delete("/categories/{category_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_category(
    category_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_category(tenant_id, category_id)
    return Response(status_code=_NO_CONTENT)


# --- Products ---------------------------------------------------------------
@router.post("/products", response_model=ProductResponse, status_code=201, dependencies=[_WRITE])
async def create_product(
    payload: CreateProductRequest, service: MenuServiceDep, tenant_id: TenantDep
) -> ProductResponse:
    prod = await service.create_product(
        tenant_id, payload.category_id, payload.name, payload.description, payload.image_url
    )
    return ProductResponse.model_validate(prod, from_attributes=True)


@router.get("/products", response_model=list[ProductResponse], dependencies=[_READ])
async def list_products(
    service: MenuServiceDep,
    tenant_id: TenantDep,
    category_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> list[ProductResponse]:
    prods = await service.list_products(tenant_id, category_id=category_id, active=active)
    return [ProductResponse.model_validate(p, from_attributes=True) for p in prods]


@router.get("/products/{product_id}", response_model=ProductResponse, dependencies=[_READ])
async def get_product(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> ProductResponse:
    prod = await service.get_product(tenant_id, product_id)
    return ProductResponse.model_validate(prod, from_attributes=True)


@router.patch("/products/{product_id}", response_model=ProductResponse, dependencies=[_WRITE])
async def update_product(
    product_id: uuid.UUID,
    payload: UpdateProductRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> ProductResponse:
    prod = await service.update_product(
        tenant_id, product_id, payload.model_dump(exclude_unset=True)
    )
    return ProductResponse.model_validate(prod, from_attributes=True)


@router.delete("/products/{product_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_product(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_product(tenant_id, product_id)
    return Response(status_code=_NO_CONTENT)


# --- Prices (per branch) ----------------------------------------------------
@router.get(
    "/products/{product_id}/prices",
    response_model=list[ProductPriceResponse],
    dependencies=[_READ],
)
async def list_prices(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> list[ProductPriceResponse]:
    prices = await service.list_prices(tenant_id, product_id)
    return [ProductPriceResponse.model_validate(p, from_attributes=True) for p in prices]


@router.put(
    "/products/{product_id}/prices/{branch_id}",
    response_model=ProductPriceResponse,
    dependencies=[_WRITE],
)
async def set_price(
    product_id: uuid.UUID,
    branch_id: uuid.UUID,
    payload: SetPriceRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> ProductPriceResponse:
    price = await service.set_price(
        tenant_id, product_id, branch_id, payload.price, payload.is_active
    )
    return ProductPriceResponse.model_validate(price, from_attributes=True)


@router.delete(
    "/products/{product_id}/prices/{branch_id}",
    status_code=_NO_CONTENT,
    dependencies=[_WRITE],
)
async def delete_price(
    product_id: uuid.UUID,
    branch_id: uuid.UUID,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.delete_price(tenant_id, product_id, branch_id)
    return Response(status_code=_NO_CONTENT)


# --- Variant groups / options ----------------------------------------------
@router.post(
    "/products/{product_id}/variant-groups",
    response_model=VariantGroupResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_variant_group(
    product_id: uuid.UUID,
    payload: CreateVariantGroupRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> VariantGroupResponse:
    group = await service.create_variant_group(
        tenant_id, product_id, payload.name, payload.is_required, payload.single_selection
    )
    return VariantGroupResponse.model_validate(group, from_attributes=True)


@router.get(
    "/products/{product_id}/variant-groups",
    response_model=list[VariantGroupResponse],
    dependencies=[_READ],
)
async def list_variant_groups(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> list[VariantGroupResponse]:
    groups = await service.list_variant_groups(tenant_id, product_id)
    return [VariantGroupResponse.model_validate(g, from_attributes=True) for g in groups]


@router.patch(
    "/variant-groups/{group_id}", response_model=VariantGroupResponse, dependencies=[_WRITE]
)
async def update_variant_group(
    group_id: uuid.UUID,
    payload: UpdateVariantGroupRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> VariantGroupResponse:
    group = await service.update_variant_group(
        tenant_id, group_id, payload.model_dump(exclude_unset=True)
    )
    return VariantGroupResponse.model_validate(group, from_attributes=True)


@router.delete("/variant-groups/{group_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_variant_group(
    group_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_variant_group(tenant_id, group_id)
    return Response(status_code=_NO_CONTENT)


@router.post(
    "/variant-groups/{group_id}/options",
    response_model=VariantOptionResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_variant_option(
    group_id: uuid.UUID,
    payload: CreateVariantOptionRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> VariantOptionResponse:
    option = await service.create_variant_option(
        tenant_id, group_id, payload.name, payload.extra_price, payload.is_active
    )
    return VariantOptionResponse.model_validate(option, from_attributes=True)


@router.get(
    "/variant-groups/{group_id}/options",
    response_model=list[VariantOptionResponse],
    dependencies=[_READ],
)
async def list_variant_options(
    group_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> list[VariantOptionResponse]:
    options = await service.list_variant_options(tenant_id, group_id)
    return [VariantOptionResponse.model_validate(o, from_attributes=True) for o in options]


@router.patch(
    "/variant-options/{option_id}",
    response_model=VariantOptionResponse,
    dependencies=[_WRITE],
)
async def update_variant_option(
    option_id: uuid.UUID,
    payload: UpdateVariantOptionRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> VariantOptionResponse:
    option = await service.update_variant_option(
        tenant_id, option_id, payload.model_dump(exclude_unset=True)
    )
    return VariantOptionResponse.model_validate(option, from_attributes=True)


@router.delete(
    "/variant-options/{option_id}", status_code=_NO_CONTENT, dependencies=[_WRITE]
)
async def delete_variant_option(
    option_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_variant_option(tenant_id, option_id)
    return Response(status_code=_NO_CONTENT)


# --- Product variants (sellable SKUs) --------------------------------------
@router.get(
    "/products/{product_id}/variants",
    response_model=list[ProductVariantResponse],
    dependencies=[_READ],
)
async def list_product_variants(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> list[ProductVariantResponse]:
    variants = await service.list_product_variants(tenant_id, product_id)
    return [ProductVariantResponse.model_validate(v, from_attributes=True) for v in variants]


@router.post(
    "/products/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_product_variant(
    product_id: uuid.UUID,
    payload: CreateProductVariantRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> ProductVariantResponse:
    variant = await service.create_product_variant(
        tenant_id, product_id, payload.name, payload.variant_option_ids
    )
    return ProductVariantResponse.model_validate(variant, from_attributes=True)


@router.patch(
    "/variants/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[_WRITE],
)
async def update_product_variant(
    variant_id: uuid.UUID,
    payload: UpdateProductVariantRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> ProductVariantResponse:
    variant = await service.update_product_variant(
        tenant_id, variant_id, payload.model_dump(exclude_unset=True)
    )
    return ProductVariantResponse.model_validate(variant, from_attributes=True)


@router.delete(
    "/variants/{variant_id}", status_code=_NO_CONTENT, dependencies=[_WRITE]
)
async def delete_product_variant(
    variant_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_product_variant(tenant_id, variant_id)
    return Response(status_code=_NO_CONTENT)


# --- Addons & product<->addon ----------------------------------------------
@router.post("/addons", response_model=AddonResponse, status_code=201, dependencies=[_WRITE])
async def create_addon(
    payload: CreateAddonRequest, service: MenuServiceDep, tenant_id: TenantDep
) -> AddonResponse:
    addon = await service.create_addon(
        tenant_id, payload.name, payload.price, payload.is_active
    )
    return AddonResponse.model_validate(addon, from_attributes=True)


@router.get("/addons", response_model=list[AddonResponse], dependencies=[_READ])
async def list_addons(
    service: MenuServiceDep, tenant_id: TenantDep, active: bool | None = None
) -> list[AddonResponse]:
    addons = await service.list_addons(tenant_id, active=active)
    return [AddonResponse.model_validate(a, from_attributes=True) for a in addons]


@router.patch("/addons/{addon_id}", response_model=AddonResponse, dependencies=[_WRITE])
async def update_addon(
    addon_id: uuid.UUID,
    payload: UpdateAddonRequest,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> AddonResponse:
    addon = await service.update_addon(
        tenant_id, addon_id, payload.model_dump(exclude_unset=True)
    )
    return AddonResponse.model_validate(addon, from_attributes=True)


@router.delete("/addons/{addon_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_addon(
    addon_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_addon(tenant_id, addon_id)
    return Response(status_code=_NO_CONTENT)


@router.get(
    "/products/{product_id}/addons",
    response_model=list[AddonResponse],
    dependencies=[_READ],
)
async def list_product_addons(
    product_id: uuid.UUID, service: MenuServiceDep, tenant_id: TenantDep
) -> list[AddonResponse]:
    addons = await service.list_product_addons(tenant_id, product_id)
    return [AddonResponse.model_validate(a, from_attributes=True) for a in addons]


@router.post(
    "/products/{product_id}/addons/{addon_id}",
    status_code=_NO_CONTENT,
    dependencies=[_WRITE],
)
async def attach_addon(
    product_id: uuid.UUID,
    addon_id: uuid.UUID,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.attach_addon(tenant_id, product_id, addon_id)
    return Response(status_code=_NO_CONTENT)


@router.delete(
    "/products/{product_id}/addons/{addon_id}",
    status_code=_NO_CONTENT,
    dependencies=[_WRITE],
)
async def detach_addon(
    product_id: uuid.UUID,
    addon_id: uuid.UUID,
    service: MenuServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.detach_addon(tenant_id, product_id, addon_id)
    return Response(status_code=_NO_CONTENT)
