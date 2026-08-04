## 1. Esquema y migración

- [x] 1.1 Agregar `default_station_id` (`Uuid`, nullable, FK a `kitchen_stations.id` con `ondelete="SET NULL"`, indexado) a `IngredientModel` en `backend/src/restaurante/modules/recipes/infrastructure/models.py`, con comentario explicando el desajuste tenant/branch y que solo alimenta la sugerencia (design §4)
- [x] 1.2 Generar la migración `0043_ingredient_default_station.py` con `alembic revision --autogenerate`, revisar que solo contenga el `add_column` + FK y que el `downgrade` la elimine limpiamente
- [x] 1.3 Verificar que `migrations/env.py` ya importe los modelos de `recipes` (registrarlo si no) y correr `alembic upgrade head` + `downgrade -1` + `upgrade head` contra la base local

## 2. Backend — insumo con estación por defecto

- [x] 2.1 Agregar `default_station_id: uuid.UUID | None` a la entidad `Ingredient` en `recipes/domain/entities.py` y a la firma del puerto de creación/actualización en `recipes/domain/ports.py`
- [x] 2.2 Mapear el campo en `recipes/infrastructure/repositories.py` (lectura y escritura), incluido el `None` explícito para poder limpiarlo
- [x] 2.3 Agregar el campo a los esquemas de request y response de insumos en `recipes/infrastructure/api/schemas.py`
- [x] 2.4 Validar en el caso de uso de `recipes/application/use_cases/manage_recipes.py` que la estación exista en el tenant, respondiendo 404 cuando no, siguiendo el patrón ya usado para `unit_of_measure_id`
- [x] 2.5 Tests en `backend/tests/modules/`: crear insumo con estación, actualizar, limpiar a `null`, rechazar estación inexistente con 404, y que borrar la estación deje el insumo con `default_station_id` nulo (spec `recipes-management`)

## 3. Backend — endpoint de sugerencia

- [x] 3.1 Definir la entidad de resultado en `kitchen/domain/entities.py`: estaciones sugeridas (`station_id`, `station_name`, `tasks`, `from_variants`, diffs de deriva) e insumos sin asignar (`ingredient_id`, `name`, `default_station_in_other_branch`)
- [x] 3.2 Agregar el método de lectura al puerto en `kitchen/domain/ports.py` e implementarlo en `kitchen/infrastructure/repositories.py`: unión de `recipe_items` de todas las variantes del producto, join a `ingredients`, agrupado por `default_station_id`, insumos deduplicados por id (design §5, §6)
- [x] 3.3 Filtrar a las estaciones de la sede activa y devolver como no asignado —marcado— todo insumo cuyo default viva en otra sede (spec "The suggestion is scoped to the active branch")
- [x] 3.4 Calcular la deriva contra las filas de `product_stations` ya guardadas: tareas que la receta implica y la copia no tiene, y tareas guardadas que la receta ya no implica (design §3)
- [x] 3.5 Caso de uso `suggest_product_stations` en `kitchen/application/use_cases/manage_kitchen.py`, estrictamente de lectura — no escribe `product_stations` bajo ninguna rama
- [x] 3.6 Esquema de respuesta en `kitchen/infrastructure/api/schemas.py` y endpoint `GET /kitchen/products/{product_id}/station-suggestion` en `kitchen/infrastructure/api/router.py`, con el `response_model` correcto y reusando el permiso de configuración de cocina ya existente — sin permisos nuevos (design §7)
- [x] 3.7 Tests del endpoint: agrupación por estación, unión entre variantes, deduplicación de insumo compartido, `unassigned_ingredients`, producto sin receta → 200 vacío, producto inexistente → 404, aislamiento por tenant → 404, estación de otra sede marcada, 403 sin permiso y 401 sin auth
- [x] 3.8 Test explícito de que llamar la sugerencia no altera ninguna fila de `product_stations` (el contrato central del cambio)
- [x] 3.9 Tests de deriva: receta ganó insumo, receta perdió insumo, tarea que no es insumo ("Emplatar") reportada pero jamás borrada, y mapeo en sincronía → ambas listas vacías

## 4. Frontend — estación por defecto del insumo

- [x] 4.1 Agregar `default_station_id` al tipo de insumo y a las llamadas de creación/actualización en `front/src/services/inventory.api.ts` (o el servicio donde vivan los insumos), con su test en `services/__tests__/`
- [x] 4.2 Cargar las estaciones de la sede activa para el selector, reutilizando lo que ya expone `stores/kitchen.ts` en vez de una lista fija
- [x] 4.3 Selector de estación en el editor de insumos de `front/src/views/InventoryView.vue`: tag mono de dos letras coherente con el rail del KDS (el color queda reservado para calor y estado), permitiendo limpiarlo
- [x] 4.4 Estado vacío: sin estaciones configuradas, el selector se muestra vacío con una pista hacia configuración de cocina y guardar sin estación sigue funcionando
- [x] 4.5 Tests de store/vista para asignar, limpiar y el caso sin estaciones

## 5. Frontend — derivar y aviso de deriva

- [x] 5.1 Agregar `getStationSuggestion(productId)` a `front/src/services/kitchen.api.ts` con su tipo de respuesta, más test en `services/__tests__/kitchen.api.spec.ts`
- [x] 5.2 Exponer la sugerencia desde `front/src/stores/kitchen.ts` sin escribirla en el estado de mapeos guardados (la sugerencia es un borrador, no dato persistido)
- [x] 5.3 Botón "Derivar de la receta" en el panel de asignación producto→estación de `front/src/components/kitchen/KitchenSetup.vue`: precarga estaciones marcadas y `tasks` rellenadas, todo editable antes de confirmar
- [x] 5.4 Guardar solo al confirmar, por las llamadas de attach/detach que el panel ya usa; cancelar deja el mapeo existente intacto
- [x] 5.5 Listar los `unassigned_ingredients` en el panel con la nota que apunta al editor de insumos, marcando los que tienen su default en otra sede
- [x] 5.6 Aviso de deriva por estación con el diff de tareas, ofreciendo "Derivar de la receta" como forma de reconciliar; ausente cuando no hay diferencias, y jamás auto-aplicado
- [x] 5.7 Estado "nada que derivar" cuando el producto no tiene receta, dejando disponible la asignación manual
- [x] 5.8 Tests de componente: precarga, edición antes de guardar, cancelar sin efecto, aviso de deriva presente/ausente, y que ninguna de esas rutas dispare un guardado

## 6. Datos demo y cierre

- [x] 6.1 Asignar `default_station_id` a los insumos del dataset demo en `backend/scripts/seed_demo.py`, manteniéndolo idempotente, para que la derivación se pueda probar en vivo (design, Open Questions)
- [ ] 6.2 Correr `poetry run pytest`, `poetry run ruff check .` y `poetry run mypy src` en verde
- [x] 6.3 Correr los tests del frontend en verde
- [ ] 6.4 Verificación manual de punta a punta: asignar estación a dos insumos de estaciones distintas → derivar en un producto → confirmar → comprobar que las chits del KDS muestran el desglose → editar la receta → comprobar que aparece el aviso de deriva y que la comanda ya abierta no cambió

## 7. Correcciones salidas de la prueba manual

Tres huecos que sólo aparecieron al usarlo de verdad: la derivación estaba en la pantalla
equivocada, la configuración de cocina era hostil, y la tarea derivada perdía la cantidad.

- [x] 7.1 Mover "Sugerir desde la receta" a `front/src/components/carta/StationsPanel.vue`: el gate de activación manda a la carta, no a Cocina, y el encabezado de ese archivo ya decía por qué la asignación vive ahí
- [x] 7.2 Agregar edición de `tasks` al panel de la carta (lista separada por comas): era lo que faltaba para responder "¿qué le pongo a cada estación?"
- [x] 7.3 Llevar aviso de deriva e insumos sin estación al mismo panel
- [x] 7.4 Sacar la asignación producto↔estación de `KitchenSetup.vue`: con la receta a mano en la carta, mantenerla en dos sitios dejaba el peor de los dos (spec `frontend-kitchen`, REMOVED con razón y migración)
- [x] 7.5 Rehacer `KitchenSetup.vue`: arranca por "Platos que nadie prepara" con enlace a la carta; orden del pase con flechas en vez de un campo numérico; renombrar en su sitio; estados vacíos que explican
- [x] 7.6 La tarea derivada lleva la cantidad y su unidad (`Carne de res 300 g`), con los ceros de escala recortados
- [x] 7.7 Variantes con cantidades distintas listan todas (`150 g / 300 g`) en vez de inventar una sola; iguales no se repiten
- [x] 7.8 Tests: 10 nuevos en `StationsPanel` (tareas + derivación), 10 nuevos en `KitchenSetup`, 5 nuevos de cantidad en `test_station_suggestion`; retirado `KitchenSetup.derive.spec.ts`
- [x] 7.9 Specs actualizados: nuevo delta `frontend-menu`, `frontend-kitchen` reescrito, requisito de cantidad en `recipe-station-derivation`
