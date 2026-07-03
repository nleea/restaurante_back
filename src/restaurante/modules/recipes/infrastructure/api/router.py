"""Recipes API: ingredient catalog + per-variant bill of materials (BOM).

Reads require `recipes.read`; writes require `recipes.manage` (RBAC). Every
operation is scoped to the tenant resolved by the subdomain middleware.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.recipes.infrastructure.api.deps import (
    RecipesServiceDep,
    TenantDep,
)
from restaurante.modules.recipes.infrastructure.api.schemas import (
    AddRecipeItemRequest,
    CreateIngredientRequest,
    IngredientResponse,
    RecipeCardResponse,
    RecipeDetailResponse,
    RecipeItemResponse,
    UpdateIngredientRequest,
    UpdateRecipeItemRequest,
    UpsertRecipeDetailRequest,
)

router = APIRouter(prefix="/recipes", tags=["recipes"])

_READ = Depends(require_permission("recipes.read"))
_WRITE = Depends(require_permission("recipes.manage"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Ingredients ------------------------------------------------------------
@router.post(
    "/ingredients",
    response_model=IngredientResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_ingredient(
    payload: CreateIngredientRequest, service: RecipesServiceDep, tenant_id: TenantDep
) -> IngredientResponse:
    ingredient = await service.create_ingredient(
        tenant_id, payload.name, payload.unit_of_measure_id, category=payload.category
    )
    return IngredientResponse.model_validate(ingredient, from_attributes=True)


@router.get(
    "/ingredients", response_model=list[IngredientResponse], dependencies=[_READ]
)
async def list_ingredients(
    service: RecipesServiceDep, tenant_id: TenantDep, active: bool | None = None
) -> list[IngredientResponse]:
    items = await service.list_ingredients(tenant_id, active=active)
    return [IngredientResponse.model_validate(i, from_attributes=True) for i in items]


@router.get(
    "/ingredients/{ingredient_id}",
    response_model=IngredientResponse,
    dependencies=[_READ],
)
async def get_ingredient(
    ingredient_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> IngredientResponse:
    ingredient = await service.get_ingredient(tenant_id, ingredient_id)
    return IngredientResponse.model_validate(ingredient, from_attributes=True)


@router.patch(
    "/ingredients/{ingredient_id}",
    response_model=IngredientResponse,
    dependencies=[_WRITE],
)
async def update_ingredient(
    ingredient_id: uuid.UUID,
    payload: UpdateIngredientRequest,
    service: RecipesServiceDep,
    tenant_id: TenantDep,
) -> IngredientResponse:
    ingredient = await service.update_ingredient(
        tenant_id, ingredient_id, payload.model_dump(exclude_unset=True)
    )
    return IngredientResponse.model_validate(ingredient, from_attributes=True)


@router.delete(
    "/ingredients/{ingredient_id}",
    response_model=IngredientResponse,
    dependencies=[_WRITE],
)
async def deactivate_ingredient(
    ingredient_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> IngredientResponse:
    ingredient = await service.deactivate_ingredient(tenant_id, ingredient_id)
    return IngredientResponse.model_validate(ingredient, from_attributes=True)


# --- Recipe items (BOM) -----------------------------------------------------
@router.post(
    "/variants/{variant_id}/items",
    response_model=RecipeItemResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def add_recipe_item(
    variant_id: uuid.UUID,
    payload: AddRecipeItemRequest,
    service: RecipesServiceDep,
    tenant_id: TenantDep,
) -> RecipeItemResponse:
    item = await service.add_recipe_item(
        tenant_id,
        variant_id,
        payload.ingredient_id,
        payload.quantity,
        payload.unit_of_measure_id,
    )
    return RecipeItemResponse.model_validate(item, from_attributes=True)


@router.get(
    "/variants/{variant_id}/items",
    response_model=list[RecipeItemResponse],
    dependencies=[_READ],
)
async def list_recipe_items(
    variant_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> list[RecipeItemResponse]:
    items = await service.list_recipe_items(tenant_id, variant_id)
    return [RecipeItemResponse.model_validate(i, from_attributes=True) for i in items]


@router.patch(
    "/items/{item_id}", response_model=RecipeItemResponse, dependencies=[_WRITE]
)
async def update_recipe_item(
    item_id: uuid.UUID,
    payload: UpdateRecipeItemRequest,
    service: RecipesServiceDep,
    tenant_id: TenantDep,
) -> RecipeItemResponse:
    item = await service.update_recipe_item(
        tenant_id, item_id, payload.model_dump(exclude_unset=True)
    )
    return RecipeItemResponse.model_validate(item, from_attributes=True)


@router.delete("/items/{item_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_recipe_item(
    item_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_recipe_item(tenant_id, item_id)
    return Response(status_code=_NO_CONTENT)


# --- Recipe details + card (cook-facing) --------------------------------------
@router.put(
    "/variants/{variant_id}/details",
    response_model=RecipeDetailResponse,
    dependencies=[_WRITE],
)
async def upsert_recipe_detail(
    variant_id: uuid.UUID,
    payload: UpsertRecipeDetailRequest,
    service: RecipesServiceDep,
    tenant_id: TenantDep,
) -> RecipeDetailResponse:
    detail = await service.upsert_recipe_detail(
        tenant_id,
        variant_id,
        steps=payload.steps,
        allergens=list(payload.allergens),
        photo_label=payload.photo_label,
    )
    return RecipeDetailResponse.model_validate(detail, from_attributes=True)


@router.get(
    "/variants/{variant_id}/details",
    response_model=RecipeDetailResponse,
    dependencies=[_READ],
)
async def get_recipe_detail(
    variant_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> RecipeDetailResponse:
    detail = await service.get_recipe_detail(tenant_id, variant_id)
    return RecipeDetailResponse.model_validate(detail, from_attributes=True)


@router.get(
    "/variants/{variant_id}/card",
    response_model=RecipeCardResponse,
    dependencies=[_READ],
)
async def get_recipe_card(
    variant_id: uuid.UUID, service: RecipesServiceDep, tenant_id: TenantDep
) -> RecipeCardResponse:
    card = await service.get_recipe_card(tenant_id, variant_id)
    return RecipeCardResponse.model_validate(card, from_attributes=True)
