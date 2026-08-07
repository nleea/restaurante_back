## Why

Derivar las tareas de cocina desde la receta dejó tres cabos sueltos que sólo se ven cocinando:

1. **La chit no distingue variantes.** Las tareas viven en `product_stations`, que es por
   producto, y la receta es por variante. Un plato con sencilla (150 g) y doble (300 g) produce
   `"Carne de res 150 g / 300 g"`, y esa cadena se congela igual en el ticket de las dos. El
   cocinero de la doble lee dos cantidades y una está mal. `route_order` **ya sabe** la variante
   del ítem; lo que le falta es poder relacionar la tarea con su línea de receta.
2. **Un insumo puede ir a dos estaciones.** El arroz se cocina o se fríe; el pescado se asa o se
   apana. `ingredients.default_station_id` es uno solo, así que la sugerencia manda el arroz frito
   a la plancha y hay que corregirlo a mano en cada plato.
3. **Las cantidades se leen en unidad de inventario.** La receta guarda `0.150 kg` porque el
   inventario se lleva en kg; en el pase eso debería decir `150 g`. Nadie pesa 0.15 kg de carne.

Las tres comparten raíz: **una tarea derivada no recuerda de qué línea de receta salió.** Es una
cadena opaca. Con esa relación, las tres se resuelven.

## What Changes

- **Tareas estructuradas.** `product_stations.tasks` pasa de `list[str]` a una lista de objetos
  `{label, ingredient_id?}`. Las derivadas llevan su insumo; las escritas a mano (`"Emplatar"`) no
  llevan nada y siguen siendo texto. La lectura tolera la forma vieja, así que no hay backfill.
- **La chit se resuelve por variante.** `route_order` sustituye la cantidad de cada tarea con
  insumo por la de la **variante pedida**. `order_item_stations.tasks` sigue siendo `list[str]`:
  el ticket es texto plano ya resuelto y el KDS no cambia.
  Una tarea cuyo insumo no está en la receta de esa variante **no se emite** — decirle al cocinero
  que ponga algo que el plato no lleva es peor que no decírselo.
- **Override de estación por línea de receta.** `recipe_items` gana `station_id` nullable. La
  derivación usa `COALESCE(línea.station_id, insumo.default_station_id)`: el default cubre el caso
  normal, el override existe para el arroz que hoy se fríe.
- **Cantidades en unidad de cocina.** Una cantidad menor que 1 se muestra en la sub-unidad de su
  familia (`0.150 kg` → `150 g`), usando `base_unit_id` y `conversion_factor`, que ya existen en
  `units_of_measure`. Sin tabla de conversiones quemada en el código.
- **El editor de tareas pasa a filas.** En el panel de estaciones de la carta, cada tarea es una
  fila (para conservar su `ingredient_id` al editar la etiqueta) en vez de una cadena separada por
  comas.
- **BREAKING (interno, sin datos afectados)**: el cuerpo de `POST /kitchen/product-stations` y
  `PATCH /kitchen/product-stations/{id}` acepta la forma nueva de `tasks`; la vieja se sigue
  aceptando y se normaliza.

## Capabilities

### New Capabilities
- `variant-aware-kitchen-tasks`: que la comanda que llega a la estación diga la cantidad de la
  variante que se pidió — la resolución en el ruteo, la omisión de lo que la variante no lleva, y
  el formato en unidad de cocina.

### Modified Capabilities
- `recipes-management`: una línea de receta puede fijar su estación, sobreponiéndose al default
  del insumo.
- `recipe-station-derivation`: la sugerencia agrupa por la estación de la línea cuando la hay, y
  devuelve tareas con el insumo del que salieron.
- `kitchen-management`: `product_stations.tasks` es estructurado y `route_order` lo resuelve
  contra la receta de la variante.
- `frontend-menu`: el editor de tareas del panel de estaciones pasa a filas y conserva el insumo.
- `frontend-inventory`: sin cambios de requisito; el selector de estación por insumo pasa a ser
  explícitamente un **default** que una receta puede sobreponer.

## Impact

- **Base de datos**: `recipe_items.station_id` (nullable, FK, `ON DELETE SET NULL`). Ninguna
  columna cambia de tipo: `tasks` ya es JSON.
- **Backend**: `kitchen` (entidad de tarea, lectura tolerante, resolución en `route_order`,
  sugerencia), `recipes` (línea con estación), `catalog` (resolución de sub-unidad).
- **Frontend**: editor de tareas por filas, selector de estación por línea en el editor de recetas.
- **Riesgo principal**: `route_order` es el camino crítico de toda comanda. La resolución no puede
  fallar ni vaciar un ticket; ante cualquier duda emite la etiqueta sin cantidad.
