## Context

`derive-stations-from-recipes` conectó la receta con las estaciones, y al usarlo aparecieron tres
huecos que comparten una sola causa: **una tarea es una cadena opaca**. Nadie puede preguntarle de
qué línea de receta salió, así que no se puede resolver por variante, ni respetar un override de
estación, ni reformatear su cantidad.

Estado del que se parte:

| Dato | Forma | Ámbito |
|---|---|---|
| `product_stations.tasks` | `list[str]` JSON | producto |
| `order_item_stations.tasks` | `list[str]` JSON, copia congelada al enrutar | ítem de orden |
| `recipe_items` | `(variant, ingredient, quantity, uom)` | **variante** |
| `ingredients.default_station_id` | FK nullable | tenant |

`route_order` (`manage_kitchen.py`) ya itera `for item_id, variant_id, branch_id in items`: la
variante está ahí, sin usar. `units_of_measure` ya tiene `base_unit_id` y `conversion_factor`, y el
seed ya crea `g` como sub-unidad de `kg` (factor 0.001) y `ml` de `L`.

## Goals / Non-Goals

**Goals:**
- Que la chit de la doble diga 300 g y la de la sencilla 150 g.
- Que un insumo pueda ir a otra estación en un plato concreto sin dejar de tener default.
- Que las cantidades se lean como las lee un cocinero, sin quemar conversiones en el código.
- No romper ninguna asignación existente ni exigir backfill.

**Non-Goals:**
- Cambiar el KDS. El ticket sigue siendo texto plano ya resuelto.
- Mover `tasks` a una tabla propia. Sigue siendo JSON en `product_stations`.
- Conversión general de unidades (recetas en libras, densidades). Sólo la sub-unidad de la familia.
- Tocar el consumo de inventario o el costeo, que leen `recipe_items` por su lado.

## Decisions

### 1. La tarea estructurada vive en la configuración; el ticket sigue siendo texto

`product_stations.tasks`: `[{label, ingredient_id?}]`. `order_item_stations.tasks`: `list[str]`.

*Por qué la asimetría*: la configuración necesita la relación para poder resolver; el ticket ya
está resuelto y lo lee una persona bajo presión. Estructurar el ticket obligaría a tocar el KDS,
el board, la comanda y el driver sin ganar nada.

*Sin migración*: la columna ya es JSON. La lectura acepta `str` (forma vieja → label sin insumo) y
`dict`. Cero backfill, cero ventana de incompatibilidad.

*Alternativa descartada*: tabla `product_station_tasks`. Correcta en abstracto, pero son ≤10 filas
por mapeo que siempre se leen y escriben juntas; una tabla añade joins a `route_order`, que es el
camino crítico de toda comanda.

### 2. El override va en la línea de receta, no en una tabla de excepciones

`recipe_items.station_id` nullable. La derivación agrupa por
`COALESCE(línea.station_id, insumo.default_station_id)`.

*Por qué ahí*: la pregunta "¿dónde se trabaja el arroz?" no tiene respuesta global, la tiene
**por plato** — y la línea de receta ES el par (plato, insumo). El default sigue cubriendo el caso
normal, así que nadie tiene que llenar el override para los 22 insumos que no lo necesitan.

*`ON DELETE SET NULL`*: borrar una estación no puede bloquear ni borrar recetas; caer al default
del insumo es la degradación correcta.

### 3. Una tarea cuyo insumo no está en la variante NO se emite

*Por qué*: las tareas son por producto y la receta por variante, así que un mapeo puede arrastrar
un insumo que la sencilla lleva y la doble no. Emitirlo le diría al cocinero que ponga algo que
ese plato no lleva — un error de comida, peor que una línea de menos. Omitir es lo que la receta
de esa variante realmente dice.

*Riesgo asumido*: si alguien deriva desde una variante y luego pide otra que comparte estación
pero no el insumo, verá menos renglones. Es correcto, pero se documenta porque sorprende.

### 4. La resolución degrada, nunca falla

Cualquier problema resolviendo una cantidad emite la etiqueta sola y sigue. `route_order` es el
camino crítico de toda comanda: un ticket sin cantidad es un inconveniente, un ticket que no se
crea es un plato que nadie cocina con el cliente esperando.

### 5. La unidad de cocina sale de los datos que ya existen

Si la cantidad es `< 1` y su unidad tiene una sub-unidad en la familia (una unidad cuyo
`base_unit_id` apunta a ella), se convierte dividiendo por su `conversion_factor`: `0.150 kg` →
`150 g`. Si es `>= 1`, se queda como está — `1.5 kg` se lee bien.

*Por qué el umbral en 1*: es donde el número deja de tener ceros a la izquierda que nadie pesa.
`1500 g` no es mejor que `1.5 kg`.

*Alternativa descartada*: tabla de conversiones en el código (`kg→g`, `L→ml`). Duplicaría en
Python algo que la base ya modela, y se rompería con la primera unidad que alguien añada.

### 6. El editor de tareas pasa a filas

Una cadena separada por comas no puede conservar el `ingredient_id` al reescribir la etiqueta.
Cada tarea es una fila; la derivada guarda su insumo aunque le cambien el nombre.

*Coste*: el panel de la carta es angosto y una lista de filas ocupa más. Se asume: sin la relación
no hay resolución por variante, que es el objetivo entero.

## Risks / Trade-offs

- **`route_order` es el camino crítico** → La resolución no añade round-trips por ticket: se lee
  la receta de la variante una vez por ítem y se reutiliza para todas sus estaciones. Degrada a
  etiqueta sin cantidad ante cualquier fallo (§4), con test dedicado.
- **Lectura tolerante de dos formas** → Un único punto de normalización en el repositorio de
  cocina; ni el caso de uso ni la API ven `str` crudo. Test con una fila en forma vieja.
- **Menos renglones en la chit de una variante** (§3) → Es lo correcto y va documentado; el panel
  de la carta muestra de qué variantes salió cada tarea.
- **El umbral de 1 es una convención** → Vive en una sola función con tests; cambiarlo es una
  línea.

## Migration Plan

1. Migración `0044`: `recipe_items.station_id` nullable con FK `ON DELETE SET NULL`. Sin backfill.
2. Backend cocina: entidad de tarea + lectura/escritura tolerante. Nada cambia de comportamiento
   todavía (las tareas viejas siguen siendo labels sin insumo).
3. Resolución de unidad de cocina, con sus tests, aislada.
4. `route_order` resuelve por variante.
5. Derivación: `COALESCE` de estación + `ingredient_id` en la respuesta.
6. Recetas: `station_id` por línea, extremo a extremo.
7. Frontend: editor de tareas por filas; selector de estación por línea.
8. `seed_demo` al día.
9. **Rollback**: todo es aditivo. La columna puede quedarse inerte y la lectura tolerante sigue
   entendiendo las dos formas, así que revertir el código no deja datos ilegibles.

## Open Questions

- ¿El panel debería avisar cuando una tarea derivada quedará fuera de alguna variante (§3)? Se
  puede saber: la sugerencia ya conoce `from_variants`. Inclinación: sí, pero en un paso posterior.
- ¿Vale la pena mostrar la cantidad por variante en el panel (`Sencilla 150 g · Doble 300 g`) en
  vez de la lista plana? Inclinación: sí cuando haya más de una, pero primero medir si estorba.
