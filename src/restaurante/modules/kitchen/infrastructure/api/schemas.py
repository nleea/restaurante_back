"""Pydantic schemas for the Kitchen API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

# One itemized station task ("Carne de hamburguesa"); lists are bounded so a docket
# component stays glanceable. The service trims and drops empties.
TaskName = Annotated[str, Field(min_length=1, max_length=60)]

# --- Responses --------------------------------------------------------------


class KitchenStationResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    position: int
    is_active: bool


class RouteOrderResponse(BaseModel):
    """Qué entró a la cocina y qué no pudo.

    `unrouted` casi siempre está vacío —una variante no se vende sin estación— pero cuando no lo
    está es lo único que importa de esta respuesta: un plato cobrado que nadie va a preparar.
    """

    tickets: list[TicketResponse] = Field(default_factory=list)
    unrouted: list[str] = Field(default_factory=list)


class UnroutableProductResponse(BaseModel):
    """Un producto que ninguna estación prepara: hoy es invisible hasta que alguien lo paga."""

    product_id: uuid.UUID
    name: str
    category_name: str | None = None
    #: Cuántas de sus variantes se están vendiendo ya. >0 es lo urgente.
    active_variants: int


class StationTaskModel(BaseModel):
    """Un renglón de lo que una estación le debe a un plato.

    `ingredient_id` es lo que permite resolver la cantidad contra la receta de la variante
    pedida al enrutar. Sin él la tarea es un paso escrito a mano y viaja verbatim.
    """

    label: str = Field(min_length=1, max_length=60)
    ingredient_id: uuid.UUID | None = None


class SuggestedTaskResponse(BaseModel):
    label: str
    ingredient_id: uuid.UUID
    #: Ya formateadas en unidad de cocina; más de una cuando las variantes no coinciden.
    amounts: list[str] = []


class SuggestedStationResponse(BaseModel):
    """Una estación que la receta implica, con lo que le debería y su deriva."""

    station_id: uuid.UUID
    station_name: str
    #: Los insumos que esta estación trabaja, unidos entre variantes.
    tasks: list[SuggestedTaskResponse] = []
    from_variants: list[str] = []
    #: Tareas que la receta implica hoy y la asignación guardada no tiene.
    missing_from_saved: list[str] = []
    #: Tareas guardadas que la receta ya no implica (incluidas las que no son insumos).
    saved_no_longer_implied: list[str] = []


class UnassignedIngredientResponse(BaseModel):
    """Un insumo de la receta que no aporta a ninguna estación de esta sede."""

    ingredient_id: uuid.UUID
    name: str
    #: True cuando sí tiene estación por defecto, pero vive en otra sede.
    default_station_in_other_branch: bool = False


class StationSuggestionResponse(BaseModel):
    """Propuesta, no asignación: nada de esto se guarda hasta que alguien lo confirma."""

    stations: list[SuggestedStationResponse] = []
    unassigned_ingredients: list[UnassignedIngredientResponse] = []


class ProductStationResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = None
    tasks: list[StationTaskModel] = Field(default_factory=list)


class TicketResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    order_item_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    status: str
    role: str | None = None
    # Texto plano YA resuelto contra la receta de la variante pedida, congelado al enrutar. El
    # ticket no lleva la estructura: lo lee una persona bajo presión, no un programa.
    tasks: list[str] = Field(default_factory=list)
    entered_at: datetime | None = None
    ready_at: datetime | None = None
    # Free-text kitchen note from the order item ("sin lechuga"), when present.
    notes: str | None = None


# --- Requests ---------------------------------------------------------------


class CreateStationRequest(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    position: int = Field(default=0, ge=0)


class UpdateStationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


#: Se aceptan las dos formas: la nueva (objeto con su insumo) y la vieja (una cadena suelta).
#: Una cadena se normaliza a etiqueta sin insumo, que es exactamente lo que significaba, así que
#: ningún cliente anterior se rompe por este cambio.
TaskInput = Annotated[list[StationTaskModel | TaskName], Field(max_length=10)]


def normalize_task_input(tasks: list[StationTaskModel | str]) -> list[StationTaskModel]:
    return [
        StationTaskModel(label=t) if isinstance(t, str) else t for t in tasks
    ]


class AttachProductStationRequest(BaseModel):
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = Field(default=None, max_length=60)
    tasks: TaskInput = Field(default_factory=list)


class UpdateProductStationRequest(BaseModel):
    role: str | None = Field(default=None, max_length=60)
    tasks: TaskInput | None = None
