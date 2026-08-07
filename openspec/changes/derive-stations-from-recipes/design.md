## Context

Hoy conviven dos hechos sobre un mismo plato que no se hablan entre sí:

| Hecho | Tabla | Ámbito | Granularidad |
|---|---|---|---|
| De qué está hecho | `recipe_items` | `TenantScopedMixin` | **variante** |
| Quién lo cocina y qué le debe | `product_stations` (`kitchen_station_id`, `role`, `tasks`) | `TenantScopedMixin` | **producto** |
| Dónde se cocina | `kitchen_stations` | `BranchScopedMixin` | sede |

`route_order` lee exclusivamente `product_stations`; un producto sin fila ahí no llega a ninguna
pantalla de cocina. `product_stations.tasks` es una lista JSON de texto libre que hoy se teclea a
mano y no tiene ninguna relación declarada con los insumos de la receta.

El insumo es el único dato que ambos lados comparten. Si cada insumo declara en qué estación se
trabaja, la asignación completa de un plato — estaciones **y** su desglose de tareas — se vuelve
derivable de su receta.

Restricciones vigentes: arquitectura hexagonal (`API → application → domain`, `infrastructure`
implementa puertos, el dominio no conoce el framework); identificadores en inglés y prosa en
español; el catálogo RBAC es código y `require_permission` lee la tabla, así que un permiso nuevo
sin `python -m scripts.seed` da 403 a todo el mundo.

## Goals / Non-Goals

**Goals:**
- Que asignar estaciones a un plato nuevo parta de la receta en vez de una hoja en blanco.
- Que el desglose de tareas del KDS tenga una fuente declarada, y que su divergencia con la
  receta sea visible en vez de silenciosa.
- Cerrar por el lado del flujo de trabajo el hueco que produce productos sin ruta, sin tocar
  `route_order`.
- Absorber el desajuste tenant/branch sin propagarlo a datos nuevos.

**Non-Goals:**
- Cambiar `route_order` o cualquier parte del ruteo. `product_stations` sigue siendo su única
  fuente de verdad.
- Cambiar la regla de activación de variante: `variant_product_has_station()` y
  `variant_has_recipe()` se quedan tal cual, como requisitos hermanos independientes.
- Tocar el consumo de inventario, el costeo o la carta pública.
- Rediseñar el ámbito de `product_stations` (tenant vs. branch). Es deuda previa; este cambio no
  la agranda ni la resuelve.
- Estación por línea de receta (un insumo, dos estaciones según el plato). Ver Open Questions.

## Decisions

### 1. La estación vive en el insumo, no en la línea de receta

`ingredients.default_station_id` (nullable, FK a `kitchen_stations`, `ON DELETE SET NULL`).

*Por qué*: la relación real que estamos capturando es "la carne se trabaja en la parrilla", que
es una propiedad del insumo y del montaje de la cocina, no de cada plato que lo usa. Ponerlo en
`recipe_items` obligaría a repetir el mismo dato en cada plato que lleva carne — que es
exactamente el trabajo manual que este cambio elimina.

*Alternativa descartada*: `recipe_items.station_id`. Máxima expresividad, cero economía: N platos
× M insumos entradas a mantener. Se puede añadir después como override sin migrar nada de esto.

*`SET NULL` y no `RESTRICT`*: borrar una estación es una operación de configuración de cocina; no
debe quedar bloqueada por insumos, y perder una sugerencia es reparable en un clic.

### 2. Sugerir, nunca derivar en vivo

`product_stations` sigue siendo la fuente de verdad escrita. El endpoint calcula y devuelve; solo
un humano confirmando escribe filas.

*Por qué*: derivar al leer haría que agregar un insumo a una receta reruteara **comandas ya
abiertas** — el cocinero vería aparecer tareas en una chit en curso. La cocina necesita que lo
que ya salió sea estable. Además hace el ruteo dependiente de dos módulos más en el camino
crítico de `route_order`.

*Alternativa descartada*: `tasks` nullable con semántica "null = derivar al leer, lista = override".
Elegante en apariencia, pero mete un modo implícito en un dato que el cocinero lee bajo presión, y
sigue teniendo el problema de la comanda viva.

### 3. La copia se guarda; la deriva se comunica

Al confirmar, las tareas se copian a `product_stations.tasks`. Cuando la receta cambia después, la
copia **no** se toca: el endpoint devuelve, por estación, qué tareas implica ahora la receta que
la copia no tiene y cuáles tiene la copia que la receta ya no implica. El panel lo muestra; el
sistema no actúa.

*Por qué*: `tasks` contiene legítimamente pasos que no son insumos ("Emplatar", "Sellar al vacío")
y redacciones deliberadas ("Tocineta ahumada" donde el insumo se llama "Tocineta"). Un
re-sincronizado automático los borraría. La deriva es un hecho del negocio, no un error a
corregir solo.

### 4. El desajuste tenant/branch se absorbe en el consumidor

`ingredients` es tenant-scoped y `kitchen_stations` es branch-scoped, así que
`ingredients.default_station_id` apunta desde el nivel tenant a una fila de una sede. Es el mismo
defecto que `product_stations` ya tiene hoy.

**Decisión**: mantener el FK directo (consistente con el precedente) y hacer branch-aware al
**consumidor**: el endpoint filtra a las estaciones de la sede activa y reporta como
*no asignado* — marcado — todo insumo cuyo default vive en otra sede.

*Por qué se puede*: el default nunca lo lee `route_order`; solo alimenta una sugerencia que un
humano revisa. El peor caso multi-sede es una sugerencia incompleta, no un dato corrupto ni una
comanda mal ruteada.

*Alternativa descartada*: guardar nombre o código de estación y resolver por sede. `kitchen_stations`
no tiene columna `code` — solo `name` — y resolver por nombre se rompe al renombrar. Habría que
introducir un código estable, que es un cambio propio y mayor que este.

### 5. Unión entre variantes, no por variante

La receta es por variante y la estación por producto (comentado a propósito en
`menu/infrastructure/repositories.py:541`: quién cocina algo no cambia con el tamaño). La
sugerencia hace la **unión** de los `recipe_items` de todas las variantes del producto.

*Por qué unión y no la variante base*: si la variante grande mete un insumo de otra estación, esa
estación hace falta de verdad; omitirla reproduce el defecto de producto sin ruta a menor escala.
Los insumos se deduplican por id, así que un insumo compartido produce una sola tarea.

### 6. Lecturas cruzadas por repositorio, no acoplamiento de servicios

El caso de uso vive en `kitchen` y su repositorio lee `RecipeItemModel` e `IngredientModel`
directamente, siguiendo el patrón ya establecido por `variant_has_recipe()` y
`variant_product_has_station()` en el repositorio de `menu`.

*Por qué*: es el precedente del repo para exactamente esta forma de consulta, y evita inyectar el
servicio de recetas en el de cocina para una lectura de solo lectura.

### 7. Sin permisos nuevos

El endpoint reusa el permiso que ya gobierna la configuración de cocina; el `default_station_id`
del insumo viaja por los endpoints de insumos existentes bajo `recipes.manage`.

*Por qué*: `require_permission` consulta la tabla y el catálogo es código. Un permiso nuevo sin
correr `python -m scripts.seed` en cada entorno deja la pantalla en 403 para todos, incluido el
admin — trampa ya documentada en este repo.

## Risks / Trade-offs

- **La copia de tareas se desincroniza igual que hoy** → El aviso de deriva la hace visible en el
  mismo panel donde se arregla, con la acción de derivar a un clic. Se cambia desincronización
  silenciosa por desincronización anunciada; no se elimina, y esa es la decisión (§3).
- **Un insumo, dos estaciones según el plato** (la carne va a parrilla en la hamburguesa pero a
  la fría en una ensalada) → El modelo actual no lo expresa; la sugerencia propondrá la estación
  equivocada en ese plato y la persona la corrige antes de guardar. Como la sugerencia nunca
  escribe sola, el error no llega a producción. Un `recipe_items.station_id` opcional lo
  resolvería después sin migrar nada de este cambio.
- **`default_station_id` apuntando a otra sede en multi-sede** → El consumidor lo filtra y lo
  marca (§4). Impacto máximo: sugerencia incompleta.
- **La gente puede seguir sin asignar estación a ningún insumo** → El cambio no obliga a nada; sin
  insumos con estación la sugerencia sale vacía y todo sigue funcionando como hoy. La adopción se
  empuja con el aviso de insumos sin estación en el propio panel, no con una validación dura.
- **El endpoint recorre variantes → items → insumos por producto** → Es una configuración puntual
  fuera del camino de la comanda, con una sola consulta con joins acotada a un producto. No entra
  en `route_order` ni en el board.

## Migration Plan

1. **Migración**: agregar `ingredients.default_station_id` (nullable, FK `ON DELETE SET NULL`).
   Registrar el módulo en `migrations/env.py` si el autogenerate no lo ve. Sin backfill: todos los
   insumos existentes arrancan sin estación y la sugerencia sale vacía hasta que alguien los
   asigne. No hay ventana de incompatibilidad porque nada lee la columna todavía.
2. **Backend recetas**: entidad, puerto, repositorio, esquemas y router de insumos aceptan y
   devuelven `default_station_id`, validando que la estación exista.
3. **Backend cocina**: caso de uso y endpoint de sugerencia, con la lectura cruzada y el cálculo
   de deriva.
4. **Frontend**: selector en el editor de insumos; luego el botón de derivar y el aviso de deriva
   en configuración de cocina, que ya tiene datos que consumir.
5. **Rollback**: los pasos 2–4 son aditivos y se revierten solos. La columna puede quedarse
   inerte sin romper nada; `alembic downgrade` la elimina si se quiere limpiar.

## Open Questions

- ¿Debería `demo-seed-data` (`scripts.seed_demo`) asignar estaciones a los insumos del dataset
  demo, para que la derivación se pueda probar en vivo sin configurarla a mano? Inclinación: sí,
  como último paso, y es barato.
- ¿El aviso de deriva debería aparecer también en el board del KDS o solo en configuración?
  Inclinación: solo en configuración — el cocinero no debe distraerse con estado de configuración
  mientras trabaja.
- ¿Vale la pena un `recipe_items.station_id` opcional como override por plato? No en este cambio;
  se decide cuando exista un caso real de insumo con dos estaciones.
