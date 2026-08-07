## Why

La receta ya sabe de qué está hecho un plato y la asignación de estaciones ya sabe quién lo
cocina, pero los dos hechos viven separados: el módulo `recipes` no menciona `station` ni una
sola vez. La consecuencia es que la lista de tareas que ve el cocinero en el KDS
(`product_stations.tasks`) se teclea a mano plato por plato, se desincroniza en silencio cuando
cambia la receta, y un producto nuevo puede quedar sin ninguna fila en `product_stations` — que
es exactamente el estado que deja un plato **sin ruta** en `route_order` (el defecto ya visto en
producción: 2 productos, 6 órdenes afectadas).

Los insumos son el único dato que ambos lados comparten, así que basta con saber en qué estación
se trabaja cada insumo para poder **proponer** la asignación completa de un plato, con su lista
de tareas ya desglosada, en vez de pedirla en blanco.

## What Changes

- **Insumo con estación por defecto.** `ingredients` gana `default_station_id` (nullable, FK a
  `kitchen_stations`, `ON DELETE SET NULL`): en qué estación se trabaja ese insumo. Se lee y
  escribe por los endpoints de insumos existentes bajo el permiso `recipes.manage` ya vigente.
- **Nuevo endpoint de sugerencia.** `GET /kitchen/products/{product_id}/station-suggestion`
  hace la unión de los `recipe_items` de **todas** las variantes del producto, agrupa los insumos
  por la estación por defecto de cada uno y devuelve estaciones propuestas con sus tareas ya
  desglosadas, más el conjunto de insumos que todavía no tienen estación.
- **Botón "Sugerir desde la receta"** en el panel de estaciones de la carta: precarga el
  formulario de asignación con la sugerencia. La persona confirma y recién ahí se escriben filas de
  `product_stations`. Nunca guarda solo.
- **Aviso de deriva.** El panel compara las `tasks` guardadas contra la sugerencia vigente y
  avisa cuando la receta cambió desde la última asignación, mostrando el diff.
- **Selector de estación** en el editor de insumos del tablero de inventario.
- No hay cambios en `route_order`: `product_stations` sigue siendo su única fuente de verdad.
- Sin permisos nuevos (uno nuevo exigiría re-sembrar el catálogo RBAC y daría 403 a todos).
- No hay cambios que rompan compatibilidad: la columna es nullable y el resto es aditivo.

## Capabilities

### New Capabilities
- `recipe-station-derivation`: derivar de la receta de un producto qué estaciones lo preparan y
  qué tarea le debe cada una — el endpoint de sugerencia, su agrupación por insumo, su
  comportamiento por sede y el contrato de que sugiere sin escribir.

### Modified Capabilities
- `recipes-management`: "Manage ingredients" incorpora `default_station_id` al crear, actualizar
  y leer un insumo, incluida la validación de que la estación exista en el tenant.
- `frontend-menu`: el panel de estaciones del editor de producto incorpora la edición de tareas,
  la derivación desde receta, el aviso de deriva y los insumos sin estación.
- `frontend-kitchen`: la configuración deja de asignar productos —eso vive en la carta, junto al
  plato— y pasa a montar la línea (crear, renombrar, reordenar) y a mostrar qué platos siguen sin
  que nadie los prepare.
- `frontend-inventory`: el editor de insumos incorpora el selector de estación por defecto.

## Impact

- **Base de datos**: nueva migración con `ingredients.default_station_id`. Ninguna columna se
  elimina ni cambia de tipo.
- **Backend**: `recipes` (entidad `Ingredient`, puerto y repositorio, esquemas y router de
  insumos); `kitchen` (nuevo caso de uso de sugerencia, lectura cruzada a `recipe_items` e
  `ingredients` al estilo de `variant_has_recipe`, nuevo endpoint y esquema de respuesta).
- **Frontend**: cliente de API de cocina e inventario, store de cocina, panel de configuración de
  producto→estación, editor de insumos del tablero de inventario.
- **Fuera de alcance**: `route_order` y el ruteo en general; la regla de activación de variante
  (`variant_product_has_station` y `variant_has_recipe` se quedan como están); consumo de
  inventario.
- **Riesgo conocido a documentar**: `ingredients` es tenant-scoped y `kitchen_stations` es
  branch-scoped, igual que el `product_stations` que ya existe. El desajuste se absorbe en el
  consumidor, no en el esquema (ver design.md).
