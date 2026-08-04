"""Framework-free domain entities of the Kitchen module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KitchenStation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    position: int = 0
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class RoutingResult:
    """Qué entró a la cocina y qué NO pudo entrar.

    Antes esto era sólo la lista de tickets, y un ítem sin estación producía cero tickets sin
    decir nada: enrutar devolvía éxito y el plato quedaba cobrado y sin cocinar. Los que sí
    pueden prepararse entran igual —el cliente está esperando— pero el hueco viaja con nombre
    propio para que alguien pueda actuar.
    """

    tickets: list[OrderItemStation] = field(default_factory=list)
    #: Nombres de los productos que no llegaron a ninguna estación.
    unrouted: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UnroutableProduct:
    """Un producto que no puede llegar a la cocina: nadie tiene asignado prepararlo.

    Existe porque el hueco es invisible por naturaleza. Un producto sin estación se ve en la
    carta igual que cualquier otro y sólo deja de existir en el instante en que la cocina
    debería haberlo recibido — con el pedido ya cobrado.

    `active_variants` es lo que separa lo urgente de lo pendiente: sin variantes activas es una
    ficha a medio crear; con ellas es algo que se está vendiendo ahora mismo y nadie cocina.
    """

    product_id: uuid.UUID
    name: str
    category_name: str | None
    active_variants: int


@dataclass(frozen=True)
class StationTask:
    """Un renglón de lo que una estación le debe a un plato.

    `ingredient_id` es lo que separa una tarea derivada de un paso escrito a mano. Con él, el
    ruteo puede resolver la cantidad contra la receta de la VARIANTE pedida — que es lo único que
    distingue "Carne de res 150 g" de "Carne de res 300 g" en la chit de la sencilla y la doble.
    Sin él (`"Emplatar"`, `"Sellar al vacío"`) la tarea es texto y viaja verbatim.

    Sobrevive al renombre: cambiarle la etiqueta a una tarea derivada no la desconecta de su
    insumo, porque quien cocina llama "Carne" a lo que el inventario llama "Carne de res".
    """

    label: str
    ingredient_id: uuid.UUID | None = None


@dataclass
class ProductStation:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = None
    # Lo que esta estación le debe al producto. Estructurado (a diferencia del ticket, que ya va
    # resuelto a texto) porque aquí todavía hace falta saber de qué insumo salió cada renglón.
    tasks: list[StationTask] = field(default_factory=list)
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class SuggestedTask:
    """Una tarea propuesta: el insumo del que sale, y lo que se verá en la chit.

    `label` es el nombre a secas — la cantidad NO se guarda en él, porque depende de la variante
    que se pida y eso sólo se sabe al enrutar. `amounts` existe sólo para que el panel muestre lo
    que va a producir: con una sola variante es una cantidad, y con sencilla y doble son las dos.
    """

    label: str
    ingredient_id: uuid.UUID
    #: Cantidades ya formateadas en unidad de cocina, una por variante distinta.
    amounts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SuggestedStation:
    """Una estación que la receta del producto implica, con lo que le debería.

    `tasks` sale de los nombres de los insumos cuya estación por defecto es ésta, unidos entre
    todas las variantes del producto. Los dos diffs son contra lo que YA está guardado en
    `product_stations`: existen para que la deriva se vea, no para repararla sola — una tarea
    que no es insumo ("Emplatar") aparece en `saved_no_longer_implied` y aun así nadie la borra.
    """

    station_id: uuid.UUID
    station_name: str
    tasks: list[SuggestedTask] = field(default_factory=list)
    #: Variantes del producto que aportaron algún insumo a esta estación.
    from_variants: list[str] = field(default_factory=list)
    #: Tareas que la receta implica hoy y la copia guardada no tiene.
    missing_from_saved: list[str] = field(default_factory=list)
    #: Tareas guardadas que la receta ya no implica.
    saved_no_longer_implied: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UnassignedIngredient:
    """Un insumo de la receta que no aporta a ninguna estación de esta sede.

    O no tiene estación por defecto, o la tiene en otra sede — que es lo que distingue
    `default_station_in_other_branch`. Se reporta en vez de descartarse: un insumo que
    desaparece en silencio es exactamente cómo se llega a un producto sin ruta.
    """

    ingredient_id: uuid.UUID
    name: str
    default_station_in_other_branch: bool = False


@dataclass(frozen=True)
class StationSuggestion:
    """Lo que la receta de un producto propone para su asignación de estaciones.

    Estrictamente de lectura: nada de esto se escribe hasta que una persona lo confirma por las
    rutas de asignación que ya existen. `route_order` sigue leyendo sólo `product_stations`, así
    que una sugerencia que nadie acepta no cambia ni una comanda.
    """

    stations: list[SuggestedStation] = field(default_factory=list)
    unassigned_ingredients: list[UnassignedIngredient] = field(default_factory=list)


@dataclass
class OrderItemStation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_item_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    status: str = "pending"
    role: str | None = None
    # Frozen copy of the mapping's tasks at fire time (config edits never rewrite tickets).
    tasks: list[str] = field(default_factory=list)
    ready_at: datetime | None = None
    entered_at: datetime | None = None
    # Read-only free-text note from the order item ("sin lechuga") so the cook can't miss it.
    notes: str | None = None
    id: uuid.UUID | None = None


@dataclass
class KitchenEvent:
    """A ticket change worth pushing to live kitchen screens (KDS boards)."""

    type: str  # "ticket_created" | "ticket_advanced"
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    station_id: uuid.UUID
    ticket_id: uuid.UUID
    status: str
    order_id: uuid.UUID | None = None
