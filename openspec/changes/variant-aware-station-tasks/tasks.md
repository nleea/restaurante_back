## 1. Migración

- [x] 1.1 Agregar `station_id` (`Uuid`, nullable, FK a `kitchen_stations.id` con `ondelete="SET NULL"`, indexado) a `RecipeItemModel`, con comentario de por qué es override y no reemplazo del default
- [x] 1.2 Migración `0044_recipe_item_station.py`; verificar `upgrade` + `downgrade -1` + `upgrade` contra Postgres

## 2. Unidad de cocina (aislado y primero: todo lo demás lo usa)

- [x] 2.1 Helper que resuelve la sub-unidad de una familia desde `base_unit_id`/`conversion_factor`, sin tabla quemada (design §5)
- [x] 2.2 Formateo: `< 1` baja a la sub-unidad (`0.150 kg` → `150 g`), `>= 1` se queda (`1.5 kg`), sin sub-unidad se queda (`1 und`); ceros de escala recortados siempre
- [x] 2.3 Tests del formateo, incluidos los bordes: exactamente 1, sin sub-unidad, decimal real, cantidad grande

## 3. Tarea estructurada en cocina

- [x] 3.1 Entidad `StationTask{label, ingredient_id}` en `kitchen/domain/entities.py`; `ProductStation.tasks` pasa a `list[StationTask]`
- [x] 3.2 Normalización tolerante en `kitchen/infrastructure/repositories.py`: `str` → label sin insumo, `dict` → tarea completa; un solo punto, ni el caso de uso ni la API ven la forma cruda (design §1)
- [x] 3.3 Esquemas de `attach`/`update product-station` aceptan las dos formas y normalizan; la respuesta devuelve siempre la nueva
- [x] 3.4 Test con una fila guardada en forma vieja (`["Carne", "Emplatar"]`) que sigue leyéndose y enrutándose

## 4. Ruteo por variante

- [x] 4.1 Lectura en el repositorio: cantidades de la receta de una variante, indexadas por `ingredient_id` (una sola consulta por ítem, reutilizada en todas sus estaciones — design, Riesgos)
- [x] 4.2 `route_order` resuelve cada tarea contra la variante pedida antes de congelarla en el ticket
- [x] 4.3 Una tarea cuyo insumo no está en la receta de esa variante NO se emite (design §3)
- [x] 4.4 Degradación: cualquier fallo resolviendo emite la etiqueta sin cantidad y el ticket se crea igual (design §4)
- [x] 4.5 Tests: sencilla vs doble en la misma orden, paso a mano verbatim, insumo ausente omitido, degradación, idempotencia intacta

## 5. Override de estación por línea de receta

- [x] 5.1 `station_id` en la entidad `RecipeItem`, puerto, repositorio y esquemas de `recipes`
- [x] 5.2 Validar que la estación exista en el tenant (404), reusando `_require_station`
- [x] 5.3 Derivación: agrupar por `COALESCE(línea.station_id, insumo.default_station_id)`
- [x] 5.4 La sugerencia devuelve `ingredient_id` en cada tarea
- [x] 5.5 Tests: override gana, sin override cae al default, ninguno de los dos → insumo sin asignar, borrar la estación deja la línea en null

## 6. Frontend

- [x] 6.1 Tipos de `kitchen.api`: tarea estructurada en `ProductStation` y en la sugerencia
- [x] 6.2 Editor de tareas por filas en `StationsPanel.vue`, conservando `ingredient_id` al renombrar; agregar fila libre; quitar fila
- [x] 6.3 Selector de estación por línea en el editor de recetas, con el default del insumo preseleccionado y forma de volver a él
- [x] 6.4 Tests: renombrar conserva el insumo, agregar paso libre, quitar, override de línea guardado

## 7. Datos demo y cierre

- [x] 7.1 `seed_demo`: tareas derivadas con `ingredient_id`; un override de línea real (arroz frito) para que el caso se pueda ver
- [x] 7.2 `pytest`, `ruff` y `mypy` sobre lo tocado; suite completa del backend en una sola corrida
- [x] 7.3 Tests del frontend en verde
- [ ] 7.4 Verificación manual: pedir sencilla y doble del mismo plato en una orden y comprobar que cada chit lleva su cantidad
